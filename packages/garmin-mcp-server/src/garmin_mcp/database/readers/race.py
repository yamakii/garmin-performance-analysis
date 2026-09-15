"""Race readiness DB reader.

Exposes the rescued ``VDOTCalculator`` (#60) as a single aggregate read: it
combines the athlete's current fitness (VDOT, from the objective fitness curve
with ``FitnessAssessor``'s Garmin-VO2max conversion as the fallback), their
active race goal (``athlete_goals``), VDOT-derived race-time predictions, and a
progress block measuring the gap to that goal.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from garmin_mcp.analysis.race_prediction import predict_race_times
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.fitness_curve import FitnessCurveReader
from garmin_mcp.fitness.vdot import VDOTCalculator

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

# Plotted VDOT precision. The prediction history rounds every curve point to
# one decimal before predicting, so the series' own ``vdot`` is exactly the
# value its ``predicted_time_seconds`` was derived from (and neighbouring days
# that round to the same VDOT share a cache entry).
_HISTORY_VDOT_DECIMALS = 1

# How old the objective curve's latest point may be before the readiness read
# stops trusting it as "current fitness" and falls back to Garmin's VO2max
# conversion. A 90-day-old best effort is no longer a read on today's form.
_OBJECTIVE_VDOT_MAX_AGE_DAYS = 90


@functools.lru_cache(maxsize=4096)
def _predict_race_time_cached(vdot: float, distance_km: float) -> int:
    """Memoized ``VDOTCalculator.predict_race_time``.

    The prediction is a 100-iteration binary search, and a history read calls
    it once per curve day (hundreds of points) for a single distance, where
    consecutive days routinely carry the same rounded VDOT. Caching on
    ``(vdot, distance_km)`` collapses those to one search each.
    """
    return VDOTCalculator.predict_race_time(vdot, distance_km)


class RaceReader(BaseDBReader):
    """Reads race readiness (current VDOT + goal gap) from DuckDB."""

    def get_race_readiness(
        self, user_id: str = "default", lookback_weeks: int = 8
    ) -> dict[str, Any]:
        """Aggregate current VDOT, race-time predictions, and goal progress.

        Combines the athlete's current fitness (VDOT, see ``_readiness_vdot``),
        the active race goal (``athlete_goals``; ``priority='A'`` / ``status=
        'active'`` preferred, otherwise the goal with the nearest future
        ``race_date``), VDOT-based race-time predictions, and a progress block
        comparing the predicted goal-distance time against the target.

        The VDOT comes from the same curve the prediction history plots, so the
        headline prediction and that chart's last point agree (#1146); the
        Garmin VO2max conversion only stands in when the curve is missing or
        stale, and ``vdot_source`` says which of the two was used.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).
            lookback_weeks: Lookback window for fitness assessment (default 8).

        Returns:
            Dict with keys:
            - ``current_vdot``: float | None
            - ``vdot_source``: ``"objective"`` | ``"garmin_vo2max"`` | None
              (None exactly when ``current_vdot`` is None)
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
        # Read once: the curve backs both the VDOT choice and the blend.
        curve = self._objective_fitness_curve()
        current_vdot, vdot_source = self._readiness_vdot(lookback_weeks, curve)

        predicted_times: dict[str, int] = {}
        if current_vdot is not None:
            predicted_times = {
                key: VDOTCalculator.predict_race_time(current_vdot, distance_km)
                for key, distance_km in _PREDICTION_DISTANCES_KM.items()
            }

        blended_predictions = predict_race_times(current_vdot, curve)

        goal = self._active_goal(user_id)

        progress: dict[str, Any] | None = None
        if current_vdot is not None and goal is not None:
            progress = self._build_progress(current_vdot, goal)

        return {
            "current_vdot": current_vdot,
            "vdot_source": vdot_source,
            "predicted_times": predicted_times,
            "blended_predictions": blended_predictions,
            "goal": goal,
            "progress": progress,
        }

    def get_race_prediction_history(
        self, user_id: str = "default", days: int = 365
    ) -> dict[str, Any]:
        """Dated race-time predictions for the active goal race.

        There is no stored prediction history, so the series is derived: the
        objective fitness curve (``FitnessCurveReader``, a 90-day rolling max of
        performance VDOT) is a dated VDOT series, and ``predict_race_time``
        turns each of its points into the goal-distance time that VDOT implies.
        When no run splits exist the curve is empty and Garmin's own VO2max
        series stands in (converted with ``vdot_from_vo2max``), which is
        optimistic — hence the ``source`` tag, so the caller can say which
        fitness the line rests on.

        The curve runs back to the athlete's first logged run (485 daily points
        on the live database), which is neither readable as a chart nor useful
        as a read on current fitness, so the series is bounded to a trailing
        window. The window applies to whichever source is in play; the source
        itself is still chosen on the full curve, so a stale-splits athlete does
        not silently switch to the optimistic Garmin line.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).
            days: Trailing window in days (default 365). Points dated before
                ``today - days`` are dropped.

        Returns:
            Dict with keys:
            - ``goal``: the active goal dict (as in ``get_race_readiness``) or
              None when the user has no goal row.
            - ``source``: ``"objective"`` | ``"garmin_vo2max"`` | None (None
              whenever ``series`` is empty).
            - ``series``: ``[{"date", "vdot", "predicted_time_seconds",
              "gap_seconds"}, ...]`` ascending by date, one point per day
              within the trailing window. ``gap_seconds`` is
              ``predicted_time_seconds - target`` (positive means the
              prediction is slower than the target).
        """
        goal = self._active_goal(user_id)
        if goal is None:
            return {"goal": None, "source": None, "series": []}

        distance_km = goal.get("distance_km")
        target = goal.get("target_time_seconds")
        # Without a distance to predict over or a target to measure against,
        # there is nothing to plot (the gap would be meaningless).
        if not distance_km or target is None:
            return {"goal": goal, "source": None, "series": []}

        # One "today" for the whole read, so a midnight rollover cannot put two
        # different cutoffs into one series.
        cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        source, vdot_by_date = self._history_vdot_by_date(cutoff)
        if not vdot_by_date:
            return {"goal": goal, "source": None, "series": []}

        target_seconds = int(target)
        series: list[dict[str, Any]] = []
        for day, vdot in sorted(vdot_by_date.items()):
            predicted = _predict_race_time_cached(vdot, float(distance_km))
            series.append(
                {
                    "date": day,
                    "vdot": vdot,
                    "predicted_time_seconds": predicted,
                    "gap_seconds": predicted - target_seconds,
                }
            )
        return {"goal": goal, "source": source, "series": series}

    def _history_vdot_by_date(self, cutoff: str) -> tuple[str | None, dict[str, float]]:
        """Pick the dated VDOT series behind the prediction history.

        Prefers the objective curve; falls back to Garmin's VO2max series
        converted to VDOT. Both are ascending with at most one plotted point
        per day, so a date seen twice keeps its last (highest-rolling) value.
        Which source is used is decided on the *full* curve, but only points
        on or after ``cutoff`` (``YYYY-MM-DD``) are kept.
        """
        curve = self._objective_fitness_curve() or {}

        objective = curve.get("objective_curve") or []
        if objective:
            return "objective", self._vdot_by_date(
                ((point.get("date"), point.get("vdot")) for point in objective),
                cutoff,
            )

        garmin = curve.get("garmin_vo2max") or []
        if garmin:
            return "garmin_vo2max", self._vdot_by_date(
                (
                    (
                        point.get("date"),
                        (
                            VDOTCalculator.vdot_from_vo2max(float(point["value"]))
                            if point.get("value") is not None
                            else None
                        ),
                    )
                    for point in garmin
                ),
                cutoff,
            )

        return None, {}

    @staticmethod
    def _vdot_by_date(
        points: Iterable[tuple[Any, Any]],
        cutoff: str,
    ) -> dict[str, float]:
        """Collapse in-window ``(date, vdot)`` pairs to one rounded VDOT per date.

        Dates are ISO (``YYYY-MM-DD``), so the window test is a string compare.
        """
        by_date: dict[str, float] = {}
        for day, vdot in points:
            if day is None or vdot is None:
                continue
            day_str = str(day)
            if day_str < cutoff:
                continue
            by_date[day_str] = round(float(vdot), _HISTORY_VDOT_DECIMALS)
        return by_date

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

    def _readiness_vdot(
        self, lookback_weeks: int, curve: dict[str, Any] | None
    ) -> tuple[float | None, str | None]:
        """Pick the VDOT the readiness read speaks with, and name its source.

        The prediction history plots the objective fitness curve, while the
        readiness read used to speak with ``FitnessAssessor``'s Garmin-VO2max
        conversion — which runs ~10 VDOT optimistic — so the same page showed a
        headline prediction an hour faster than its own chart (#1146). Both now
        rest on the objective curve.

        Selection rule:
        1. the objective curve's latest point, when it is no older than
           ``_OBJECTIVE_VDOT_MAX_AGE_DAYS`` (a stale best effort is not a read
           on current fitness);
        2. otherwise ``FitnessAssessor`` (Garmin VO2max conversion), which is
           optimistic but always available while VO2max is recorded;
        3. ``(None, None)`` when neither exists.

        Args:
            lookback_weeks: Lookback window for the ``FitnessAssessor``
                fallback.
            curve: An already-read objective fitness curve (as returned by
                ``_objective_fitness_curve``), passed in so the readiness read
                derives the curve once and shares it with the blend.

        Returns:
            ``(vdot, source)`` where ``source`` is ``"objective"``,
            ``"garmin_vo2max"`` or None. ``vdot`` is rounded like the history
            series, so a shared curve point yields an identical prediction.
        """
        objective_vdot = self._latest_objective_vdot(curve)
        if objective_vdot is not None:
            return objective_vdot, "objective"

        garmin_vdot = self._current_vdot(lookback_weeks)
        if garmin_vdot is not None:
            return garmin_vdot, "garmin_vo2max"

        return None, None

    @staticmethod
    def _latest_objective_vdot(curve: dict[str, Any] | None) -> float | None:
        """Latest objective-curve VDOT, or None when absent or stale.

        Dates are ISO (``YYYY-MM-DD``), so both "latest" and the staleness test
        are string compares.
        """
        points = (curve or {}).get("objective_curve") or []
        dated = [
            (str(point["date"]), float(point["vdot"]))
            for point in points
            if point.get("date") is not None and point.get("vdot") is not None
        ]
        if not dated:
            return None

        day, vdot = max(dated)
        cutoff = (date.today() - timedelta(days=_OBJECTIVE_VDOT_MAX_AGE_DAYS)).strftime(
            "%Y-%m-%d"
        )
        if day < cutoff:
            return None
        return round(vdot, _HISTORY_VDOT_DECIMALS)

    def _current_vdot(self, lookback_weeks: int) -> float | None:
        """Return current VDOT from ``FitnessAssessor``, or None when unavailable.

        ``FitnessAssessor.assess`` raises ``ValueError`` when there are no
        running activities (or none suitable for VDOT estimation); that is a
        legitimate "no data" state, so it is mapped to ``None`` rather than
        propagated.
        """
        # Imported lazily to avoid a circular import: ``FitnessAssessor`` imports
        # ``database.readers.base``, which eagerly loads the readers package
        # (including this module) via ``readers/__init__``.
        from garmin_mcp.fitness.fitness_assessor import FitnessAssessor

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
