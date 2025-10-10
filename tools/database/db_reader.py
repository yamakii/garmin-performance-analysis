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

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB reader with database path."""
        if db_path is None:
            from tools.utils.paths import get_database_dir

            db_path = str(get_database_dir() / "garmin_performance.duckdb")

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

    def get_hr_efficiency_analysis(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get HR efficiency analysis from hr_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            HR efficiency data with zone distribution and training type.
            Format: {
                "primary_zone": str,
                "zone_distribution_rating": str,
                "hr_stability": str,
                "aerobic_efficiency": str,
                "training_quality": str,
                "zone2_focus": bool,
                "zone4_threshold_work": bool,
                "training_type": str,
                "zone_percentages": {
                    "zone1": float, "zone2": float, "zone3": float,
                    "zone4": float, "zone5": float
                }
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    primary_zone,
                    zone_distribution_rating,
                    hr_stability,
                    aerobic_efficiency,
                    training_quality,
                    zone2_focus,
                    zone4_threshold_work,
                    training_type,
                    zone1_percentage,
                    zone2_percentage,
                    zone3_percentage,
                    zone4_percentage,
                    zone5_percentage
                FROM hr_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            if not result:
                return None

            return {
                "primary_zone": result[0],
                "zone_distribution_rating": result[1],
                "hr_stability": result[2],
                "aerobic_efficiency": result[3],
                "training_quality": result[4],
                "zone2_focus": bool(result[5]),
                "zone4_threshold_work": bool(result[6]),
                "training_type": result[7],
                "zone_percentages": {
                    "zone1": result[8],
                    "zone2": result[9],
                    "zone3": result[10],
                    "zone4": result[11],
                    "zone5": result[12],
                },
            }

        except Exception as e:
            logger.error(f"Error getting HR efficiency analysis: {e}")
            return None

    def get_heart_rate_zones_detail(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get heart rate zones detail from heart_rate_zones table.

        Args:
            activity_id: Activity ID

        Returns:
            Heart rate zones data with boundaries and time distribution.
            Format: {
                "zones": [
                    {
                        "zone_number": int,
                        "low_boundary": int,
                        "high_boundary": int,
                        "time_in_zone_seconds": float,
                        "zone_percentage": float
                    },
                    ...
                ]
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    zone_number,
                    zone_low_boundary,
                    zone_high_boundary,
                    time_in_zone_seconds,
                    zone_percentage
                FROM heart_rate_zones
                WHERE activity_id = ?
                ORDER BY zone_number
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return None

            zones = []
            for row in result:
                zones.append(
                    {
                        "zone_number": row[0],
                        "low_boundary": row[1],
                        "high_boundary": row[2],
                        "time_in_zone_seconds": row[3],
                        "zone_percentage": row[4],
                    }
                )

            return {"zones": zones}

        except Exception as e:
            logger.error(f"Error getting heart rate zones detail: {e}")
            return None

    def get_vo2_max_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get VO2 max data from vo2_max table.

        Args:
            activity_id: Activity ID

        Returns:
            VO2 max data with precise value, fitness age, and category.
            Format: {
                "precise_value": float,
                "value": float,
                "date": str,
                "fitness_age": int,
                "category": int
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    precise_value,
                    value,
                    date,
                    fitness_age,
                    category
                FROM vo2_max
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            if not result:
                return None

            return {
                "precise_value": result[0],
                "value": result[1],
                "date": str(result[2]) if result[2] else None,
                "fitness_age": result[3],
                "category": result[4],
            }

        except Exception as e:
            logger.error(f"Error getting VO2 max data: {e}")
            return None

    def get_lactate_threshold_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get lactate threshold data from lactate_threshold table.

        Args:
            activity_id: Activity ID

        Returns:
            Lactate threshold data with HR, speed, and power metrics.
            Format: {
                "heart_rate": int,
                "speed_mps": float,
                "date_hr": str,
                "functional_threshold_power": int,
                "power_to_weight": float,
                "weight": float,
                "date_power": str
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    heart_rate,
                    speed_mps,
                    date_hr,
                    functional_threshold_power,
                    power_to_weight,
                    weight,
                    date_power
                FROM lactate_threshold
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            if not result:
                return None

            return {
                "heart_rate": result[0],
                "speed_mps": result[1],
                "date_hr": str(result[2]) if result[2] else None,
                "functional_threshold_power": result[3],
                "power_to_weight": result[4],
                "weight": result[5],
                "date_power": str(result[6]) if result[6] else None,
            }

        except Exception as e:
            logger.error(f"Error getting lactate threshold data: {e}")
            return None

    def get_splits_all(self, activity_id: int) -> dict[str, list[dict]]:
        """
        Get all split data from splits table (全22フィールド).

        Args:
            activity_id: Activity ID

        Returns:
            Complete split data with all metrics.
            Format: {
                "splits": [
                    {
                        "split_number": int,
                        "distance_km": float,
                        "role_phase": str,
                        "pace_str": str,
                        "avg_pace_seconds_per_km": float,
                        "avg_heart_rate": int,
                        "hr_zone": str,
                        "cadence": float,
                        "cadence_rating": str,
                        "power": float,
                        "power_efficiency": str,
                        "stride_length": float,
                        "ground_contact_time_ms": float,
                        "vertical_oscillation_cm": float,
                        "vertical_ratio_percent": float,
                        "elevation_gain_m": float,
                        "elevation_loss_m": float,
                        "terrain_type": str,
                        "environmental_conditions": str,
                        "wind_impact": str,
                        "temp_impact": str,
                        "environmental_impact": str
                    },
                    ...
                ]
            }
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index,
                    distance,
                    role_phase,
                    pace_str,
                    pace_seconds_per_km,
                    heart_rate,
                    hr_zone,
                    cadence,
                    cadence_rating,
                    power,
                    power_efficiency,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    terrain_type,
                    environmental_conditions,
                    wind_impact,
                    temp_impact,
                    environmental_impact
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
                        "role_phase": row[2],
                        "pace_str": row[3],
                        "avg_pace_seconds_per_km": row[4],
                        "avg_heart_rate": row[5],
                        "hr_zone": row[6],
                        "cadence": row[7],
                        "cadence_rating": row[8],
                        "power": row[9],
                        "power_efficiency": row[10],
                        "stride_length": row[11],
                        "ground_contact_time_ms": row[12],
                        "vertical_oscillation_cm": row[13],
                        "vertical_ratio_percent": row[14],
                        "elevation_gain_m": row[15],
                        "elevation_loss_m": row[16],
                        "terrain_type": row[17],
                        "environmental_conditions": row[18],
                        "wind_impact": row[19],
                        "temp_impact": row[20],
                        "environmental_impact": row[21],
                    }
                )

            return {"splits": splits}

        except Exception as e:
            logger.error(f"Error getting all splits data: {e}")
            return {"splits": []}
