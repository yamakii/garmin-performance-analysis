"""Trend narration DB reader.

Reads weekly / monthly longitudinal trend narratives (issue #789, parent #701)
from the ``trend_analyses`` table. Trend analyses are versioned (append-only):
each save inserts a new row, so a given period may have several rows. Readers
resolve the canonical result as the latest version (highest ``created_at``),
mirroring the ``weekly_reviews`` reader pattern.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)

_SELECT_COLS = (
    "analysis_id, user_id, granularity, period_start, period_end, "
    "analysis_data, created_at, agent_name, agent_version "
    "FROM trend_analyses"
)


class TrendNarrationReader(BaseDBReader):
    """Reads longitudinal trend narratives from DuckDB."""

    def get_trend_analysis(
        self, granularity: str, period_start: str, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """Get the latest version of a single trend analysis record.

        Args:
            granularity: Trend granularity (``'week'`` | ``'month'``).
            period_start: Period start (``YYYY-MM-DD``).
            user_id: Owner identifier (defaults to ``"default"``).

        Returns:
            A dict with the trend columns (date/timestamp values converted to
            ``str``) where ``analysis_data`` is JSON-decoded back into a dict, or
            ``None`` when no matching record exists.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} "
                "WHERE user_id = ? AND granularity = ? AND period_start = ? "
                "ORDER BY created_at DESC LIMIT 1",
                [user_id, granularity, period_start],
            ).fetchone()

            if row is None:
                return None

            columns = [desc[0] for desc in conn.description]
            return self._trend_row_to_dict(columns, row)

    def list_trend_analyses(
        self, granularity: str, limit: int = 12, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """List recent trend analyses (latest version per period) in period order.

        Trend analyses are versioned (multiple rows per period). This
        deduplicates to the latest version per period before applying the limit.

        Args:
            granularity: Trend granularity (``'week'`` | ``'month'``).
            limit: Maximum number of records to return (default 12).
            user_id: Owner identifier (defaults to ``"default"``).

        Returns:
            A list of trend dicts (newest period first, latest version per
            period). Each ``analysis_data`` is JSON-decoded back into a dict.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} "
                "WHERE user_id = ? AND granularity = ? "
                "QUALIFY ROW_NUMBER() OVER ("
                "PARTITION BY period_start ORDER BY created_at DESC) = 1 "
                "ORDER BY period_start DESC LIMIT ?",
                [user_id, granularity, limit],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [self._trend_row_to_dict(columns, row) for row in rows]

    def list_trend_analysis_versions(
        self, granularity: str, period_start: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """List all versions of a trend analysis for a given period.

        Args:
            granularity: Trend granularity (``'week'`` | ``'month'``).
            period_start: Period start (``YYYY-MM-DD``).
            user_id: Owner identifier (defaults to ``"default"``).

        Returns:
            A list of every version saved for the period, newest first
            (``created_at`` DESC). Each ``analysis_data`` is JSON-decoded back
            into a dict. Empty when no record exists for the period.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} "
                "WHERE user_id = ? AND granularity = ? AND period_start = ? "
                "ORDER BY created_at DESC",
                [user_id, granularity, period_start],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [self._trend_row_to_dict(columns, row) for row in rows]

    @classmethod
    def _trend_row_to_dict(cls, columns: list[str], row: tuple) -> dict[str, Any]:
        """Convert a trend_analyses row, JSON-decoding ``analysis_data``."""
        record = cls._row_to_dict(columns, row)
        raw = record.get("analysis_data")
        record["analysis_data"] = json.loads(raw) if raw is not None else None
        return record

    @staticmethod
    def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
        """Zip a row into a dict, converting date/datetime values to str."""
        record: dict[str, Any] = {}
        for col, value in zip(columns, row, strict=False):
            if isinstance(value, _dt.date | _dt.datetime):
                record[col] = str(value)
            else:
                record[col] = value
        return record
