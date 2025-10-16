"""
Metadata reader for activity queries.

Handles activity date and ID lookups.
"""

import logging

from tools.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class MetadataReader(BaseDBReader):
    """Reader for activity metadata queries."""

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
