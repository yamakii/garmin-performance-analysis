"""
Metadata reader for activity queries.

Handles activity date and ID lookups.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class MetadataReader(BaseDBReader):
    """Reader for activity metadata queries."""

    # Columns on the ``activities`` table that may be bulk-fetched via
    # ``get_bulk_activity_fields``. Used as an allowlist to prevent SQL
    # injection through dynamically interpolated column names.
    ACTIVITY_FIELD_ALLOWLIST: frozenset[str] = frozenset(
        {
            "activity_date",
            "activity_name",
            "total_distance_km",
            "total_time_seconds",
            "avg_speed_ms",
            "avg_pace_seconds_per_km",
            "avg_heart_rate",
            "max_heart_rate",
            "temp_celsius",
            "relative_humidity_percent",
            "wind_speed_kmh",
        }
    )

    def get_activity_date(self, activity_id: int) -> str | None:
        """
        Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date in YYYY-MM-DD format, or None if not found
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT activity_date FROM activities WHERE activity_id = ?",
                    [activity_id],
                ).fetchone()

            if result:
                return str(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity date: {e}")
            return None

    def query_activity_by_date(self, date: str) -> int | None:
        """
        Query activity ID by date from DuckDB.

        Args:
            date: Activity date in YYYY-MM-DD format

        Returns:
            Activity ID if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT activity_id FROM activities WHERE activity_date = ?",
                    [date],
                ).fetchone()

            if result:
                return int(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity by date: {e}")
            return None

    def get_activity_dates(self, activity_ids: list[int]) -> dict[int, str]:
        """Bulk-fetch activity dates for multiple activities in one query.

        Args:
            activity_ids: List of activity IDs

        Returns:
            Dict mapping activity_id -> activity_date (YYYY-MM-DD str).
            Activities without a stored date are omitted.
        """
        if not activity_ids:
            return {}

        placeholders = ",".join(["?"] * len(activity_ids))
        sql = (
            "SELECT activity_id, activity_date "
            f"FROM activities WHERE activity_id IN ({placeholders})"
        )
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, activity_ids).fetchall()
            return {int(row[0]): str(row[1]) for row in rows if row[1] is not None}
        except Exception as e:
            logger.error(f"Error bulk-querying activity dates: {e}")
            return {}

    def get_bulk_activity_fields(
        self, activity_ids: list[int], fields: list[str]
    ) -> dict[int, dict[str, Any]]:
        """Bulk-fetch arbitrary ``activities`` columns in a single query.

        Args:
            activity_ids: List of activity IDs
            fields: Column names to fetch. Each must be in
                ``ACTIVITY_FIELD_ALLOWLIST`` (validated to prevent SQL
                injection via dynamic column interpolation).

        Returns:
            Dict mapping activity_id -> {field: value}. Activities not found
            in the table are omitted.

        Raises:
            ValueError: If any requested field is not in the allowlist.
        """
        if not fields:
            return {}

        invalid = [f for f in fields if f not in self.ACTIVITY_FIELD_ALLOWLIST]
        if invalid:
            raise ValueError(f"Invalid activity field(s): {invalid}")

        if not activity_ids:
            return {}

        # Deduplicate fields while preserving order for stable column mapping.
        ordered_fields = list(dict.fromkeys(fields))
        columns_sql = ", ".join(ordered_fields)
        placeholders = ",".join(["?"] * len(activity_ids))
        sql = (
            f"SELECT activity_id, {columns_sql} "
            f"FROM activities WHERE activity_id IN ({placeholders})"
        )
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, activity_ids).fetchall()
            result: dict[int, dict[str, Any]] = {}
            for row in rows:
                activity_id = int(row[0])
                result[activity_id] = {
                    field: row[idx + 1] for idx, field in enumerate(ordered_fields)
                }
            return result
        except Exception as e:
            logger.error(f"Error bulk-querying activity fields: {e}")
            return {}
