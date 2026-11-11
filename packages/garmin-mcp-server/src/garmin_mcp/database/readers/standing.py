"""Current-standing DB reader (Issue #1569).

Gathers the inputs of :func:`garmin_mcp.analysis.current_standing.
build_current_standing` -- the active goals, the training blocks, the longest
recent run, the build baseline and the last 28 days of runs -- and hands them to
the pure assembly. Nothing here is stored: the view is recomputed on every call.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from garmin_mcp.analysis.current_standing import (
    RECENT_WINDOW_DAYS,
    build_current_standing,
)
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.readers.plan import PlanReader
from garmin_mcp.database.readers.training_load import TrainingLoadReader

logger = logging.getLogger(__name__)

#: The longest run counts as "proven" when it falls within this many days.
PROVEN_LONG_RUN_WINDOW_DAYS = 182


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


class StandingReader(BaseDBReader):
    """Reads the inputs of the current-standing view from DuckDB."""

    def get_current_standing(
        self, on_date: str | None = None, user_id: str = "default"
    ) -> dict[str, Any]:
        """Where the athlete stands against the goal on ``on_date``.

        Args:
            on_date: Reference day (``YYYY-MM-DD``). Defaults to today.
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            :func:`build_current_standing` output: ``on_date``, ``goals``,
            ``block``, ``remaining_steps``, ``proven``,
            ``recent_near_goal_pace`` and ``missing``.
        """
        day = (
            datetime.strptime(on_date, "%Y-%m-%d").date()
            if on_date is not None
            else date.today()
        )
        day_str = day.isoformat()

        blocks = PlanReader(str(self.db_path)).get_training_blocks(user_id=user_id)
        acwr = TrainingLoadReader(str(self.db_path)).get_acwr(end_date=day_str)
        build_baseline = acwr.get("build_baseline") or {}

        return build_current_standing(
            on_date=day_str,
            goals=self.get_active_goals(user_id=user_id),
            blocks=blocks,
            proven_long_run=self.get_proven_long_run(day_str),
            build_baseline=build_baseline,
            recent_runs=self.get_recent_runs(day_str),
        )

    def get_active_goals(self, user_id: str = "default") -> list[dict[str, Any]]:
        """``athlete_goals`` rows with status ``active``, ordered by race date."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT race_name, race_date, priority, goal_type, distance_km, "
                "target_time_seconds, status "
                "FROM athlete_goals WHERE user_id = ? AND status = 'active' "
                "ORDER BY race_date NULLS LAST, goal_id",
                [user_id],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
        goals = [dict(zip(columns, row, strict=True)) for row in rows]
        for goal in goals:
            goal["race_date"] = _iso(goal.get("race_date"))
        return goals

    def get_proven_long_run(self, on_date: str) -> dict[str, Any] | None:
        """The longest run (by distance) in the window ending on ``on_date``.

        Args:
            on_date: Reference day (``YYYY-MM-DD``), inclusive.

        Returns:
            ``{activity_id, date, distance_km, duration_seconds,
            avg_pace_sec_per_km, window_days}`` or None when no run falls in
            the last :data:`PROVEN_LONG_RUN_WINDOW_DAYS` days.
        """
        end = datetime.strptime(on_date, "%Y-%m-%d").date()
        start = end - timedelta(days=PROVEN_LONG_RUN_WINDOW_DAYS - 1)
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT activity_id, activity_date, total_distance_km, "
                "total_time_seconds, avg_pace_seconds_per_km "
                "FROM activities "
                "WHERE activity_date BETWEEN ? AND ? "
                "AND total_distance_km IS NOT NULL "
                "ORDER BY total_distance_km DESC, activity_date DESC LIMIT 1",
                [start.isoformat(), end.isoformat()],
            ).fetchone()
        if row is None:
            return None
        return {
            "activity_id": int(row[0]),
            "date": _iso(row[1]),
            "distance_km": round(float(row[2]), 2),
            "duration_seconds": int(row[3]) if row[3] is not None else None,
            "avg_pace_sec_per_km": (
                round(float(row[4]), 1) if row[4] is not None else None
            ),
            "window_days": PROVEN_LONG_RUN_WINDOW_DAYS,
        }

    def get_recent_runs(self, on_date: str) -> list[dict[str, Any]]:
        """Runs of the 28 days ending on ``on_date`` (inclusive), oldest first.

        Returns:
            ``[{date, distance_km, avg_pace_sec_per_km, avg_hr,
            training_type}]``; ``training_type`` comes from ``hr_efficiency``
            and is None when that row is absent.
        """
        end = datetime.strptime(on_date, "%Y-%m-%d").date()
        start = end - timedelta(days=RECENT_WINDOW_DAYS - 1)
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT a.activity_date, a.total_distance_km, "
                "a.avg_pace_seconds_per_km, a.avg_heart_rate, h.training_type "
                "FROM activities a "
                "LEFT JOIN hr_efficiency h ON h.activity_id = a.activity_id "
                "WHERE a.activity_date BETWEEN ? AND ? "
                "ORDER BY a.activity_date, a.activity_id",
                [start.isoformat(), end.isoformat()],
            ).fetchall()
        return [
            {
                "date": _iso(row[0]),
                "distance_km": float(row[1]) if row[1] is not None else None,
                "avg_pace_sec_per_km": float(row[2]) if row[2] is not None else None,
                "avg_hr": row[3],
                "training_type": row[4],
            }
            for row in rows
        ]
