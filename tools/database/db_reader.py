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

    def get_splits_pace_hr(self, activity_id: int) -> dict[str, list[dict]]:
        """
        Get pace and heart rate data for all splits from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            Dict with 'splits' key containing list of split data with pace and HR
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index,
                    distance,
                    pace_seconds_per_km,
                    heart_rate
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return {"splits": []}

            splits = []
            for row in result:
                splits.append(
                    {
                        "split_number": row[0],
                        "distance_km": row[1],
                        "avg_pace_seconds_per_km": row[2],
                        "avg_heart_rate": row[3],
                    }
                )

            return {"splits": splits}

        except Exception as e:
            logger.error(f"Error getting splits pace/HR data: {e}")
            return {"splits": []}

    def get_splits_form_metrics(self, activity_id: int) -> dict[str, list[dict]]:
        """
        Get form metrics (GCT, VO, VR) for all splits from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            Dict with 'splits' key containing list of split data with form metrics
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return {"splits": []}

            splits = []
            for row in result:
                splits.append(
                    {
                        "split_number": row[0],
                        "ground_contact_time_ms": row[1],
                        "vertical_oscillation_cm": row[2],
                        "vertical_ratio_percent": row[3],
                    }
                )

            return {"splits": splits}

        except Exception as e:
            logger.error(f"Error getting splits form metrics: {e}")
            return {"splits": []}

    def get_splits_elevation(self, activity_id: int) -> dict[str, list[dict]]:
        """
        Get elevation data for all splits from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            Dict with 'splits' key containing list of split data with elevation
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index,
                    elevation_gain,
                    elevation_loss,
                    terrain_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return {"splits": []}

            splits = []
            for row in result:
                splits.append(
                    {
                        "split_number": row[0],
                        "elevation_gain_m": row[1],
                        "elevation_loss_m": row[2],
                        "max_elevation_m": None,  # Not available in splits table
                        "min_elevation_m": None,  # Not available in splits table
                        "terrain_type": row[3],
                    }
                )

            return {"splits": splits}

        except Exception as e:
            logger.error(f"Error getting splits elevation data: {e}")
            return {"splits": []}
