"""Race readiness DB reader.

Exposes the rescued ``VDOTCalculator`` (#60) as a single aggregate read: it
combines the athlete's current fitness (VDOT, via ``FitnessAssessor``), their
active race goal (``athlete_goals``), VDOT-derived race-time predictions, and a
progress block measuring the gap to that goal.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from garmin_mcp.analysis.race_prediction import predict_race_times
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.fitness_curve import FitnessCurveReader
from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor
from garmin_mcp.training_plan.vdot import VDOTCalculator

logger = logging.getLogger(__name__)

# Standard race distances (km) used for VDOT-based predictions.
_PREDICTION_DISTANCES_KM: dict[str, float] = {
    "race_5k": 5.0,
    "race_10k": 10.0,
    "half": 21.0975,
    "full": 42.195,
}

# Status thresholds on the predicted-vs-target gap (seconds). Provisional:
# gap <= -60s (predicted at least a minute faster than target) -> ahead;
# |gap| < 60s -> on_track; gap > 60s (predicted slower than target) -> behind.
_AHEAD_THRESHOLD_S = -60
_ON_TRACK_THRESHOLD_S = 60


class RaceReader(BaseDBReader):
    """Reads race readiness (current VDOT + goal gap) from DuckDB."""

    def get_race_readiness(
        self, user_id: str = "default", lookback_weeks: int = 8
    ) -> dict[str, Any]:
        """Aggregate current VDOT, race-time predictions, and goal progress.

        Combines the athlete's current fitness (VDOT from ``FitnessAssessor``),
        the active race goal (``athlete_goals``; ``priority='A'`` / ``status=
        'active'`` preferred, otherwise the goal with the nearest future
        ``race_date``), VDOT-based race-time predictions, and a progress block
        comparing the predicted goal-distance time against the target.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).
            lookback_weeks: Lookback window for fitness assessment (default 8).

        Returns:
            Dict with keys:
            - ``current_vdot``: float | None
            - ``predicted_times``: {race_5k, race_10k, half, full} in seconds
              (empty dict when ``current_vdot`` is None)
            - ``goal``: {race_name, race_date (str), distance_km,
              target_time_seconds} | None
            - ``progress``: {predicted_time_seconds, gap_seconds,
              pace_gap_sec_per_km, weeks_remaining, status} | None
              (present only when both ``current_vdot`` and ``goal`` exist)
            - ``blended_predictions``: per-distance blend of the VDOT estimate
              and the objective fitness curve with a confidence tag (see
              ``analysis.race_prediction.predict_race_times``); keyed like
              ``predicted_times`` (or ``{"insufficient_data": True}`` when
              neither source is available)
        """
        current_vdot = self._current_vdot(lookback_weeks)

        predicted_times: dict[str, int] = {}
        if current_vdot is not None:
            predicted_times = {
                key: VDOTCalculator.predict_race_time(current_vdot, distance_km)
                for key, distance_km in _PREDICTION_DISTANCES_KM.items()
            }

        blended_predictions = predict_race_times(
            current_vdot, self._objective_fitness_curve()
        )

        goal = self._active_goal(user_id)

        progress: dict[str, Any] | None = None
        if current_vdot is not None and goal is not None:
            progress = self._build_progress(current_vdot, goal)

        return {
            "current_vdot": current_vdot,
            "predicted_times": predicted_times,
            "blended_predictions": blended_predictions,
            "goal": goal,
            "progress": progress,
        }

    def _objective_fitness_curve(self) -> dict[str, Any] | None:
        """Read the objective fitness curve, mapping any failure to ``None``.

        The blended prediction degrades gracefully to VDOT-only when the curve
        is unavailable (no splits, read error), so a failure here must not break
        the readiness read.
        """
        try:
            return FitnessCurveReader(
                db_path=str(self.db_path)
            ).get_objective_fitness_curve()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Objective fitness curve unavailable: {e}")
            return None

    def _current_vdot(self, lookback_weeks: int) -> float | None:
        """Return current VDOT from ``FitnessAssessor``, or None when unavailable.

        ``FitnessAssessor.assess`` raises ``ValueError`` when there are no
        running activities (or none suitable for VDOT estimation); that is a
        legitimate "no data" state, so it is mapped to ``None`` rather than
        propagated.
        """
        try:
            summary = FitnessAssessor(db_path=str(self.db_path)).assess(
                lookback_weeks=lookback_weeks
            )
        except ValueError:
            return None
        return summary.vdot

    def _active_goal(self, user_id: str) -> dict[str, Any] | None:
        """Select the active race goal for a user.

        Preference order:
        1. ``priority='A'`` and ``status='active'`` (newest first by goal_id)
        2. Otherwise the goal with the nearest future ``race_date``.

        Returns:
            A dict with ``race_name``, ``race_date`` (str | None),
            ``distance_km``, ``target_time_seconds``, or ``None`` when no goal
            row exists for the user.
        """
        with self._get_connection() as conn:
            preferred = conn.execute(
                """
                SELECT race_name, race_date, distance_km, target_time_seconds
                FROM athlete_goals
                WHERE user_id = ? AND priority = 'A' AND status = 'active'
                ORDER BY goal_id DESC
                LIMIT 1
                """,
                [user_id],
            ).fetchone()
            if preferred is not None:
                return self._goal_row_to_dict(preferred)

            today_str = date.today().strftime("%Y-%m-%d")
            nearest = conn.execute(
                """
                SELECT race_name, race_date, distance_km, target_time_seconds
                FROM athlete_goals
                WHERE user_id = ? AND race_date >= ?
                ORDER BY race_date ASC
                LIMIT 1
                """,
                [user_id, today_str],
            ).fetchone()
            if nearest is not None:
                return self._goal_row_to_dict(nearest)

            return None

    @staticmethod
    def _goal_row_to_dict(row: tuple) -> dict[str, Any]:
        """Map a goal row to the documented dict, stringifying ``race_date``."""
        race_date = row[1]
        return {
            "race_name": row[0],
            "race_date": str(race_date) if race_date is not None else None,
            "distance_km": row[2],
            "target_time_seconds": row[3],
        }

    def _build_progress(
        self, current_vdot: float, goal: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Build the progress block comparing predicted goal time vs target.

        Returns ``None`` when the goal lacks a usable ``distance_km`` or
        ``target_time_seconds`` (gap is then meaningless).
        """
        distance_km = goal.get("distance_km")
        target = goal.get("target_time_seconds")
        if not distance_km or target is None:
            return None

        predicted = VDOTCalculator.predict_race_time(current_vdot, distance_km)
        gap_seconds = predicted - int(target)
        pace_gap_sec_per_km = round(gap_seconds / distance_km, 1)

        if gap_seconds <= _AHEAD_THRESHOLD_S:
            status = "ahead"
        elif abs(gap_seconds) < _ON_TRACK_THRESHOLD_S:
            status = "on_track"
        else:
            status = "behind"

        return {
            "predicted_time_seconds": predicted,
            "gap_seconds": gap_seconds,
            "pace_gap_sec_per_km": pace_gap_sec_per_km,
            "weeks_remaining": self._weeks_remaining(goal.get("race_date")),
            "status": status,
        }

    @staticmethod
    def _weeks_remaining(race_date_str: str | None) -> int | None:
        """Whole weeks from today until ``race_date`` (None if missing/parse fail)."""
        if not race_date_str:
            return None
        try:
            race_d = datetime.strptime(race_date_str, "%Y-%m-%d").date()
        except ValueError:
            return None
        delta_days = (race_d - date.today()).days
        return max(delta_days // 7, 0)
