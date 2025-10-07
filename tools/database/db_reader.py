"""
DuckDB Reader for Garmin Performance Data

Provides read-only access to DuckDB for querying performance data.
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

import duckdb

logger = logging.getLogger(__name__)


class GarminDBReader:
    """Read-only DuckDB access for Garmin performance data."""

    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        """Initialize DuckDB reader with database path."""
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            logger.warning(f"Database not found: {self.db_path}")

    def get_activity_date(self, activity_id: int) -> str | None:
        """
        Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date in YYYY-MM-DD format, or None if not found
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                "SELECT date FROM activities WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
            conn.close()

            if result:
                return str(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity date: {e}")
            return None

    def get_performance_section(
        self, activity_id: int, section: str
    ) -> dict[str, Any] | None:
        """
        Get specific section from performance data.

        Args:
            activity_id: Activity ID
            section: Section name (basic_metrics, heart_rate_zones, etc.)

        Returns:
            Section data as dict, or None if not found
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                f"SELECT {section} FROM performance_data WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
            conn.close()

            if result and result[0]:
                return cast(dict[str, Any], json.loads(result[0]))
            return None
        except Exception as e:
            logger.error(f"Error querying performance section: {e}")
            return None

    def get_section_analysis(
        self, activity_id: int, section_type: str
    ) -> dict[str, Any] | None:
        """
        Get section analysis from DuckDB.

        Args:
            activity_id: Activity ID
            section_type: Section type (efficiency, environment, phase, split, summary)

        Returns:
            Section analysis data as dict, or None if not found
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                "SELECT analysis_data FROM section_analyses WHERE activity_id = ? AND section_type = ?",
                [activity_id, section_type],
            ).fetchone()
            conn.close()

            if result and result[0]:
                return cast(dict[str, Any], json.loads(result[0]))
            return None
        except Exception as e:
            logger.error(f"Error querying section analysis: {e}")
            return None
