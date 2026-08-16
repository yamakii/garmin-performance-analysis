"""Hiking (山行) DB reader.

Reads hiking summaries from the dedicated ``hiking_sessions`` table (issue
#921). The table is populated by ``ingest/hiking_ingest.py`` and is
intentionally separate from ``activities`` so hikes never pollute run
aggregations.

This reader performs **no** Garmin API access: it only queries DuckDB.
``activity_date`` (a ``datetime.date``) is converted to a ``YYYY-MM-DD`` string
before returning so the result is JSON-serializable at the MCP boundary.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)

_COLUMNS = [
    "activity_id",
    "activity_date",
    "start_time_local",
    "activity_name",
    "duration_seconds",
    "elapsed_duration_seconds",
    "distance_km",
    "elevation_gain_m",
    "elevation_loss_m",
    "avg_heart_rate",
    "max_heart_rate",
    "calories",
    "ingested_at",
]


class HikingSessionsReader(BaseDBReader):
    """Reads hiking summaries from DuckDB."""

    def get_hiking_sessions(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Return hiking summaries with ``activity_date`` in ``[start, end]``.

        No Garmin access; reads only the ``hiking_sessions`` table.

        Args:
            start_date: Inclusive window start (``YYYY-MM-DD``).
            end_date: Inclusive window end (``YYYY-MM-DD``).

        Returns:
            List of dicts (one per hike, ``activity_date`` ascending). Each dict
            has the ``hiking_sessions`` columns with date/timestamp values
            converted to strings. Returns an empty list when no hike falls in
            the range.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {", ".join(_COLUMNS)}
                FROM hiking_sessions
                WHERE activity_date BETWEEN ? AND ?
                ORDER BY activity_date ASC, activity_id ASC
                """,
                [start_date, end_date],
            ).fetchall()

        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        """Map a result tuple to a dict, normalizing date/timestamp values."""
        record = dict(zip(_COLUMNS, row, strict=True))
        record["activity_date"] = _to_date_str(record["activity_date"])
        record["start_time_local"] = _to_str_or_none(record["start_time_local"])
        record["ingested_at"] = _to_str_or_none(record["ingested_at"])
        return record


def _to_date_str(value: Any) -> str | None:
    """Convert a DuckDB DATE (``datetime.date``) to ``YYYY-MM-DD`` (or None)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _to_str_or_none(value: Any) -> str | None:
    """Convert a timestamp/date value to ``str`` (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return str(value)
    return str(value)
