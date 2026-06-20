"""Strength-session (補強) DB reader.

Reads strength_training summaries from the dedicated ``strength_sessions``
table (issue #450). The table is populated by
``ingest/strength_ingest.py`` and is intentionally separate from
``activities`` so strength work does not pollute run aggregations.

This reader performs **no** Garmin API access: it only queries DuckDB.
``category_counts`` is stored as a JSON column and returned as a ``dict``;
``activity_date`` (a ``datetime.date``) is converted to a ``YYYY-MM-DD``
string before returning so the result is JSON-serializable at the MCP
boundary.
"""

from __future__ import annotations

import json
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
    "active_duration_seconds",
    "elapsed_duration_seconds",
    "avg_heart_rate",
    "max_heart_rate",
    "calories",
    "active_sets",
    "total_sets",
    "category_counts",
    "ingested_at",
]


class StrengthSessionsReader(BaseDBReader):
    """Reads strength-training summaries from DuckDB."""

    def get_strength_sessions(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Return strength summaries with ``activity_date`` in ``[start, end]``.

        No Garmin access; reads only the ``strength_sessions`` table.

        Args:
            start_date: Inclusive window start (``YYYY-MM-DD``).
            end_date: Inclusive window end (``YYYY-MM-DD``).

        Returns:
            List of dicts (one per session, ``activity_date`` ascending). Each
            dict has the ``strength_sessions`` columns with ``category_counts``
            as a ``dict`` and date/timestamp values converted to strings.
            Returns an empty list when no session falls in the range.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {", ".join(_COLUMNS)}
                FROM strength_sessions
                WHERE activity_date BETWEEN ? AND ?
                ORDER BY activity_date ASC, activity_id ASC
                """,
                [start_date, end_date],
            ).fetchall()

        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        """Map a result tuple to a dict, normalizing JSON/date/timestamp values."""
        record = dict(zip(_COLUMNS, row, strict=True))
        record["activity_date"] = _to_date_str(record["activity_date"])
        record["start_time_local"] = _to_str_or_none(record["start_time_local"])
        record["ingested_at"] = _to_str_or_none(record["ingested_at"])
        record["category_counts"] = _parse_category_counts(record["category_counts"])
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


def _parse_category_counts(value: Any) -> dict[str, Any]:
    """Return ``category_counts`` as a dict.

    DuckDB returns a JSON column as a string; parse it. Already-dict values
    (defensive) pass through, and null/unparseable values yield ``{}``.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
