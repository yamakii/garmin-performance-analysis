"""Athlete profile DB reader."""

from __future__ import annotations

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class AthleteReader(BaseDBReader):
    """Reads the athlete profile (focus + goals + retrospectives) from DuckDB."""

    def get_athlete_profile(self, user_id: str = "default") -> dict[str, Any]:
        """Get the merged athlete profile for a user.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            Dict with ``user_id``, ``current_focus``, ``focus_notes``,
            ``updated_at`` (str), ``goals`` (list) and ``retrospectives`` (list).
            When no profile row exists, ``current_focus``/``focus_notes``/
            ``updated_at`` are ``None`` and the lists are empty.
            All date/timestamp values are converted to ``str``.
        """
        with self._get_connection() as conn:
            profile_row = conn.execute(
                "SELECT current_focus, focus_notes, updated_at "
                "FROM athlete_profile WHERE user_id = ?",
                [user_id],
            ).fetchone()

            if profile_row is None:
                result: dict[str, Any] = {
                    "user_id": user_id,
                    "current_focus": None,
                    "focus_notes": None,
                    "updated_at": None,
                }
            else:
                result = {
                    "user_id": user_id,
                    "current_focus": profile_row[0],
                    "focus_notes": profile_row[1],
                    "updated_at": (
                        str(profile_row[2]) if profile_row[2] is not None else None
                    ),
                }

            goal_rows = conn.execute(
                "SELECT goal_id, race_name, race_date, priority, goal_type, "
                "distance_km, target_time_seconds, status, notes "
                "FROM athlete_goals WHERE user_id = ? ORDER BY goal_id",
                [user_id],
            ).fetchall()
            goal_columns = [desc[0] for desc in conn.description]
            result["goals"] = [
                self._row_to_dict(goal_columns, row) for row in goal_rows
            ]

            retro_rows = conn.execute(
                "SELECT retro_id, season_label, period_start, period_end, "
                "narrative, key_learnings "
                "FROM season_retrospectives WHERE user_id = ? ORDER BY retro_id",
                [user_id],
            ).fetchall()
            retro_columns = [desc[0] for desc in conn.description]
            result["retrospectives"] = [
                self._row_to_dict(retro_columns, row) for row in retro_rows
            ]

            return result

    @staticmethod
    def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
        """Zip a row into a dict, converting date/datetime values to str."""
        import datetime as _dt

        record: dict[str, Any] = {}
        for col, value in zip(columns, row, strict=False):
            if isinstance(value, _dt.date | _dt.datetime):
                record[col] = str(value)
            else:
                record[col] = value
        return record
