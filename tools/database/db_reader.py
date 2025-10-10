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

    def query_activity_by_date(self, date: str) -> int | None:
        """
        Query activity ID by date from DuckDB.

        Args:
            date: Activity date in YYYY-MM-DD format

        Returns:
            Activity ID if found, None otherwise
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                "SELECT activity_id FROM activities WHERE date = ?",
                [date],
            ).fetchone()
            conn.close()

            if result:
                return int(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity by date: {e}")
            return None

    def get_performance_section(
        self, activity_id: int, section: str
    ) -> dict[str, Any] | None:
        """
        Get specific section from performance data.

        For normalized tables (performance_trends), reads from dedicated table.
        For other sections, reads from performance_data JSON column.

        Args:
            activity_id: Activity ID
            section: Section name (basic_metrics, heart_rate_zones, performance_trends, etc.)

        Returns:
            Section data as dict, or None if not found
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            # Special handling for performance_trends: read from normalized table
            if section == "performance_trends":
                result = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        cadence_consistency,
                        fatigue_pattern,
                        warmup_splits,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        run_splits,
                        run_avg_pace_seconds_per_km,
                        run_avg_hr,
                        recovery_splits,
                        recovery_avg_pace_seconds_per_km,
                        recovery_avg_hr,
                        cooldown_splits,
                        cooldown_avg_pace_seconds_per_km,
                        cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    conn.close()
                    return None

                # Convert to dict format
                def parse_splits(splits_str):
                    return [int(s) for s in splits_str.split(",")] if splits_str else []

                data = {
                    "pace_consistency": result[0],
                    "hr_drift_percentage": result[1],
                    "cadence_consistency": result[2],
                    "fatigue_pattern": result[3],
                }

                # Add warmup_phase
                if result[4]:  # warmup_splits exists
                    data["warmup_phase"] = {
                        "splits": parse_splits(result[4]),
                        "avg_pace": result[5],
                        "avg_hr": result[6],
                    }

                # Add run_phase
                if result[7]:  # run_splits exists
                    data["run_phase"] = {
                        "splits": parse_splits(result[7]),
                        "avg_pace": result[8],
                        "avg_hr": result[9],
                    }

                # Add recovery_phase (4-phase interval training)
                if result[10]:  # recovery_splits exists
                    data["recovery_phase"] = {
                        "splits": parse_splits(result[10]),
                        "avg_pace": result[11],
                        "avg_hr": result[12],
                    }

                # Add cooldown_phase
                if result[13]:  # cooldown_splits exists
                    data["cooldown_phase"] = {
                        "splits": parse_splits(result[13]),
                        "avg_pace": result[14],
                        "avg_hr": result[15],
                    }

                conn.close()
                return data

            else:
                # Default behavior: read from performance_data JSON column
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

    def get_form_efficiency_summary(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get form efficiency summary from form_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            Form efficiency data with GCT, VO, VR metrics and ratings.
            Format: {
                "gct": {"average": float, "min": float, "max": float, "std": float,
                        "variability": float, "rating": str, "evaluation": str},
                "vo": {"average": float, "min": float, "max": float, "std": float,
                       "trend": str, "rating": str, "evaluation": str},
                "vr": {"average": float, "min": float, "max": float, "std": float,
                       "rating": str, "evaluation": str}
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    gct_average, gct_min, gct_max, gct_std, gct_variability,
                    gct_rating, gct_evaluation,
                    vo_average, vo_min, vo_max, vo_std, vo_trend,
                    vo_rating, vo_evaluation,
                    vr_average, vr_min, vr_max, vr_std,
                    vr_rating, vr_evaluation
                FROM form_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            if not result:
                return None

            return {
                "gct": {
                    "average": result[0],
                    "min": result[1],
                    "max": result[2],
                    "std": result[3],
                    "variability": result[4],
                    "rating": result[5],
                    "evaluation": result[6],
                },
                "vo": {
                    "average": result[7],
                    "min": result[8],
                    "max": result[9],
                    "std": result[10],
                    "trend": result[11],
                    "rating": result[12],
                    "evaluation": result[13],
                },
                "vr": {
                    "average": result[14],
                    "min": result[15],
                    "max": result[16],
                    "std": result[17],
                    "rating": result[18],
                    "evaluation": result[19],
                },
            }

        except Exception as e:
            logger.error(f"Error getting form efficiency summary: {e}")
            return None
