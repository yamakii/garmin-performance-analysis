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

    def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get performance trends data from performance_trends table.

        Args:
            activity_id: Activity ID

        Returns:
            Performance trends data with phase breakdowns.
            Format: {
                "pace_consistency": float,
                "hr_drift_percentage": float,
                "cadence_consistency": str,
                "fatigue_pattern": str,
                "warmup_phase": {
                    "splits": [1, 2],
                    "avg_pace": float,
                    "avg_hr": float
                },
                "run_phase": {
                    "splits": [3, 4, 5],
                    "avg_pace": float,
                    "avg_hr": float
                },
                "recovery_phase": {  # Only for 4-phase interval training
                    "splits": [6, 7],
                    "avg_pace": float,
                    "avg_hr": float
                },
                "cooldown_phase": {
                    "splits": [8],
                    "avg_pace": float,
                    "avg_hr": float
                }
            }
            None if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

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

            conn.close()

            if not result:
                return None

            # Helper function to parse splits (CSV format: '1,2,3')
            def parse_splits(splits_str: str | None) -> list[int]:
                if not splits_str:
                    return []
                return [int(s.strip()) for s in splits_str.split(",")]

            trends_data = {
                "pace_consistency": result[0],
                "hr_drift_percentage": result[1],
                "cadence_consistency": result[2],
                "fatigue_pattern": result[3],
                "warmup_phase": {
                    "splits": parse_splits(result[4]),
                    "avg_pace": result[5],
                    "avg_hr": result[6],
                },
                "run_phase": {
                    "splits": parse_splits(result[7]),
                    "avg_pace": result[8],
                    "avg_hr": result[9],
                },
                "cooldown_phase": {
                    "splits": parse_splits(result[13]),
                    "avg_pace": result[14],
                    "avg_hr": result[15],
                },
            }

            # Add recovery_phase only if it exists (4-phase interval training)
            if result[10] is not None:
                trends_data["recovery_phase"] = {
                    "splits": parse_splits(result[10]),
                    "avg_pace": result[11],
                    "avg_hr": result[12],
                }

            return trends_data

        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            return None

    def get_weather_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get weather data from activities table.

        Args:
            activity_id: Activity ID

        Returns:
            Weather data from activity.
            Format: {
                "temperature_c": float,  # External temperature in Celsius
                "temperature_f": float,  # External temperature in Fahrenheit
                "humidity": int,         # Relative humidity percentage
                "wind_speed_ms": float,  # Wind speed in meters per second
                "wind_direction": str    # Compass direction (e.g., "N", "NE", "SW")
            }
            None if activity not found or weather data unavailable.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    external_temp_c,
                    external_temp_f,
                    humidity,
                    wind_speed_ms,
                    wind_direction_compass
                FROM activities
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            if not result:
                return None

            return {
                "temperature_c": result[0],
                "temperature_f": result[1],
                "humidity": result[2],
                "wind_speed_ms": result[3],
                "wind_direction": result[4],
            }

        except Exception as e:
            logger.error(f"Error getting weather data: {e}")
            return None

    def get_section_analysis(
        self, activity_id: int, section_type: str, max_output_size: int = 10240
    ) -> dict[str, Any] | None:
        """
        Get section analysis from DuckDB.

        DEPRECATED: This function may return large amounts of data.
        Consider using extract_insights() MCP function for keyword-based
        summarized insights instead.

        Args:
            activity_id: Activity ID
            section_type: Section type (efficiency, environment, phase, split, summary)
            max_output_size: Maximum output size in bytes (default: 10KB).
                           Set to None to disable limit (backward compatibility).

        Returns:
            Section analysis data as dict, or None if not found

        Raises:
            ValueError: If output size exceeds max_output_size
        """
        import warnings

        # Show deprecation warning
        warnings.warn(
            "get_section_analysis() may return large amounts of data. "
            "Consider using extract_insights() MCP function for "
            "keyword-based summarized insights instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                "SELECT analysis_data FROM section_analyses WHERE activity_id = ? AND section_type = ?",
                [activity_id, section_type],
            ).fetchone()
            conn.close()

            if not result or not result[0]:
                return None

            output = cast(dict[str, Any], json.loads(result[0]))

            # Check output size if limit is set
            if max_output_size is not None:
                output_json = json.dumps(output, ensure_ascii=False)
                output_size = len(output_json.encode("utf-8"))

                if output_size > max_output_size:
                    raise ValueError(
                        f"Output size ({output_size} bytes) exceeds max_output_size ({max_output_size} bytes). "
                        f"Consider using extract_insights() MCP function for summarized data instead."
                    )

            return output

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            logger.error(f"Error querying section analysis: {e}")
            return None

    def get_splits_pace_hr(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """
        Get pace and heart rate data for all splits from splits table.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                           instead of per-split data. Significantly reduces output size (~80% reduction).
                           Default: False (backward compatible)

        Returns:
            Full mode (statistics_only=False):
                Dict with 'splits' key containing list of split data with pace and HR
            Statistics mode (statistics_only=True):
                Dict with aggregated statistics:
                {
                    "activity_id": int,
                    "statistics_only": True,
                    "metrics": {
                        "pace": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                        "heart_rate": {"mean": float, "median": float, "std": float, "min": float, "max": float}
                    }
                }
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            if statistics_only:
                # Statistics mode: Use DuckDB aggregate functions
                result = conn.execute(
                    """
                    SELECT
                        AVG(pace_seconds_per_km) as pace_mean,
                        MEDIAN(pace_seconds_per_km) as pace_median,
                        STDDEV(pace_seconds_per_km) as pace_std,
                        MIN(pace_seconds_per_km) as pace_min,
                        MAX(pace_seconds_per_km) as pace_max,
                        AVG(heart_rate) as hr_mean,
                        MEDIAN(heart_rate) as hr_median,
                        STDDEV(heart_rate) as hr_std,
                        MIN(heart_rate) as hr_min,
                        MAX(heart_rate) as hr_max
                    FROM splits
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                conn.close()

                if not result or result[0] is None:
                    # No data found
                    return {
                        "activity_id": activity_id,
                        "statistics_only": True,
                        "metrics": {},
                    }

                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {
                        "pace": {
                            "mean": float(result[0]) if result[0] is not None else 0.0,
                            "median": (
                                float(result[1]) if result[1] is not None else 0.0
                            ),
                            "std": float(result[2]) if result[2] is not None else 0.0,
                            "min": float(result[3]) if result[3] is not None else 0.0,
                            "max": float(result[4]) if result[4] is not None else 0.0,
                        },
                        "heart_rate": {
                            "mean": float(result[5]) if result[5] is not None else 0.0,
                            "median": (
                                float(result[6]) if result[6] is not None else 0.0
                            ),
                            "std": float(result[7]) if result[7] is not None else 0.0,
                            "min": float(result[8]) if result[8] is not None else 0.0,
                            "max": float(result[9]) if result[9] is not None else 0.0,
                        },
                    },
                }

            # Full mode: Return all split data
            splits_result = conn.execute(
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

            if not splits_result:
                return {"splits": []}

            splits = []
            for row in splits_result:
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
            if statistics_only:
                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {},
                }
            return {"splits": []}

    def get_splits_form_metrics(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """
        Get form metrics (GCT, VO, VR) for all splits from splits table.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                           instead of per-split data. Significantly reduces output size (~80% reduction).
                           Default: False (backward compatible)

        Returns:
            Full mode (statistics_only=False):
                Dict with 'splits' key containing list of split data with form metrics
            Statistics mode (statistics_only=True):
                Dict with aggregated statistics:
                {
                    "activity_id": int,
                    "statistics_only": True,
                    "metrics": {
                        "ground_contact_time": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                        "vertical_oscillation": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                        "vertical_ratio": {"mean": float, "median": float, "std": float, "min": float, "max": float}
                    }
                }
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            if statistics_only:
                # Statistics mode: Use DuckDB aggregate functions
                result = conn.execute(
                    """
                    SELECT
                        AVG(ground_contact_time) as gct_mean,
                        MEDIAN(ground_contact_time) as gct_median,
                        STDDEV(ground_contact_time) as gct_std,
                        MIN(ground_contact_time) as gct_min,
                        MAX(ground_contact_time) as gct_max,
                        AVG(vertical_oscillation) as vo_mean,
                        MEDIAN(vertical_oscillation) as vo_median,
                        STDDEV(vertical_oscillation) as vo_std,
                        MIN(vertical_oscillation) as vo_min,
                        MAX(vertical_oscillation) as vo_max,
                        AVG(vertical_ratio) as vr_mean,
                        MEDIAN(vertical_ratio) as vr_median,
                        STDDEV(vertical_ratio) as vr_std,
                        MIN(vertical_ratio) as vr_min,
                        MAX(vertical_ratio) as vr_max
                    FROM splits
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                conn.close()

                if not result or result[0] is None:
                    # No data found
                    return {
                        "activity_id": activity_id,
                        "statistics_only": True,
                        "metrics": {},
                    }

                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {
                        "ground_contact_time": {
                            "mean": float(result[0]) if result[0] is not None else 0.0,
                            "median": (
                                float(result[1]) if result[1] is not None else 0.0
                            ),
                            "std": float(result[2]) if result[2] is not None else 0.0,
                            "min": float(result[3]) if result[3] is not None else 0.0,
                            "max": float(result[4]) if result[4] is not None else 0.0,
                        },
                        "vertical_oscillation": {
                            "mean": float(result[5]) if result[5] is not None else 0.0,
                            "median": (
                                float(result[6]) if result[6] is not None else 0.0
                            ),
                            "std": float(result[7]) if result[7] is not None else 0.0,
                            "min": float(result[8]) if result[8] is not None else 0.0,
                            "max": float(result[9]) if result[9] is not None else 0.0,
                        },
                        "vertical_ratio": {
                            "mean": (
                                float(result[10]) if result[10] is not None else 0.0
                            ),
                            "median": (
                                float(result[11]) if result[11] is not None else 0.0
                            ),
                            "std": (
                                float(result[12]) if result[12] is not None else 0.0
                            ),
                            "min": (
                                float(result[13]) if result[13] is not None else 0.0
                            ),
                            "max": (
                                float(result[14]) if result[14] is not None else 0.0
                            ),
                        },
                    },
                }

            # Full mode: Return all split data
            splits_result = conn.execute(
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

            if not splits_result:
                return {"splits": []}

            splits = []
            for row in splits_result:
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
            if statistics_only:
                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {},
                }
            return {"splits": []}

    def get_splits_elevation(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """
        Get elevation data for all splits from splits table.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                           instead of per-split data. Significantly reduces output size (~80% reduction).
                           Default: False (backward compatible)

        Returns:
            Full mode (statistics_only=False):
                Dict with 'splits' key containing list of split data with elevation
            Statistics mode (statistics_only=True):
                Dict with aggregated statistics:
                {
                    "activity_id": int,
                    "statistics_only": True,
                    "metrics": {
                        "elevation_gain": {"mean": float, "median": float, "std": float, "min": float, "max": float},
                        "elevation_loss": {"mean": float, "median": float, "std": float, "min": float, "max": float}
                    }
                }
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            if statistics_only:
                # Statistics mode: Use DuckDB aggregate functions
                result = conn.execute(
                    """
                    SELECT
                        AVG(elevation_gain) as gain_mean,
                        MEDIAN(elevation_gain) as gain_median,
                        STDDEV(elevation_gain) as gain_std,
                        MIN(elevation_gain) as gain_min,
                        MAX(elevation_gain) as gain_max,
                        AVG(elevation_loss) as loss_mean,
                        MEDIAN(elevation_loss) as loss_median,
                        STDDEV(elevation_loss) as loss_std,
                        MIN(elevation_loss) as loss_min,
                        MAX(elevation_loss) as loss_max
                    FROM splits
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                conn.close()

                if not result or result[0] is None:
                    # No data found
                    return {
                        "activity_id": activity_id,
                        "statistics_only": True,
                        "metrics": {},
                    }

                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {
                        "elevation_gain": {
                            "mean": float(result[0]) if result[0] is not None else 0.0,
                            "median": (
                                float(result[1]) if result[1] is not None else 0.0
                            ),
                            "std": float(result[2]) if result[2] is not None else 0.0,
                            "min": float(result[3]) if result[3] is not None else 0.0,
                            "max": float(result[4]) if result[4] is not None else 0.0,
                        },
                        "elevation_loss": {
                            "mean": float(result[5]) if result[5] is not None else 0.0,
                            "median": (
                                float(result[6]) if result[6] is not None else 0.0
                            ),
                            "std": float(result[7]) if result[7] is not None else 0.0,
                            "min": float(result[8]) if result[8] is not None else 0.0,
                            "max": float(result[9]) if result[9] is not None else 0.0,
                        },
                    },
                }

            # Full mode: Return all split data
            splits_result = conn.execute(
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

            if not splits_result:
                return {"splits": []}

            splits = []
            for row in splits_result:
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
            if statistics_only:
                return {
                    "activity_id": activity_id,
                    "statistics_only": True,
                    "metrics": {},
                }
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

    def get_splits_all(
        self, activity_id: int, max_output_size: int = 10240
    ) -> dict[str, list[dict]]:
        """
        Get all split data from splits table (全22フィールド).

        DEPRECATED: This function returns large amounts of data.
        Consider using `export()` MCP function for large datasets,
        or use lightweight splits functions with `statistics_only=True`.

        Args:
            activity_id: Activity ID
            max_output_size: Maximum output size in bytes (default: 10KB).
                           Set to None to disable limit (backward compatibility).

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

        Raises:
            ValueError: If output size exceeds max_output_size
        """
        import warnings

        # Show deprecation warning
        warnings.warn(
            "get_splits_all() returns large amounts of data. "
            "Consider using export() MCP function for large datasets, "
            "or use lightweight splits functions (get_splits_pace_hr, etc.) "
            "with statistics_only=True parameter.",
            DeprecationWarning,
            stacklevel=2,
        )

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

            output = {"splits": splits}

            # Check output size if limit is set
            if max_output_size is not None:
                import json

                output_json = json.dumps(output, ensure_ascii=False)
                output_size = len(output_json.encode("utf-8"))

                if output_size > max_output_size:
                    raise ValueError(
                        f"Output size ({output_size} bytes) exceeds max_output_size ({max_output_size} bytes). "
                        f"Consider using export() MCP function to save data to a file instead."
                    )

            return output

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            logger.error(f"Error getting all splits data: {e}")
            return {"splits": []}

    def get_split_time_ranges(self, activity_id: int) -> list[dict[str, Any]]:
        """Get time ranges for all splits of an activity.

        Args:
            activity_id: Activity ID

        Returns:
            List of dictionaries with split time range data:
            [
                {
                    "split_index": 1,
                    "duration_seconds": 387.504,
                    "start_time_s": 0,
                    "end_time_s": 387
                },
                ...
            ]
            Empty list if activity not found.
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index,
                    duration_seconds,
                    start_time_s,
                    end_time_s
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                return []

            splits = []
            for row in result:
                splits.append(
                    {
                        "split_index": row[0],
                        "duration_seconds": row[1],
                        "start_time_s": row[2],
                        "end_time_s": row[3],
                    }
                )

            return splits

        except Exception as e:
            logger.error(f"Error getting split time ranges: {e}")
            return []

    def get_time_series_statistics(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
    ) -> dict[str, Any]:
        """Get statistics for specified metrics in time range using SQL.

        This method calculates AVG, STDDEV, MIN, MAX directly in DuckDB,
        providing significant token reduction compared to loading raw JSON.

        Args:
            activity_id: Activity ID.
            start_time_s: Start time in seconds.
            end_time_s: End time in seconds.
            metrics: List of metric column names (e.g., ['heart_rate', 'speed']).

        Returns:
            Dictionary with statistics:
            {
                "activity_id": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "statistics": {
                    "metric_name": {
                        "avg": float,
                        "std": float,
                        "min": float,
                        "max": float
                    },
                    ...
                },
                "data_points": int
            }
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            # Build SQL for statistics calculation
            stats_selects = []
            for metric in metrics:
                stats_selects.append(
                    f"AVG({metric}) as {metric}_avg, "
                    f"STDDEV({metric}) as {metric}_std, "
                    f"MIN({metric}) as {metric}_min, "
                    f"MAX({metric}) as {metric}_max"
                )

            stats_sql = ", ".join(stats_selects)

            query = f"""
            SELECT
                {stats_sql},
                COUNT(*) as data_points
            FROM time_series_metrics
            WHERE activity_id = ?
              AND timestamp_s >= ?
              AND timestamp_s < ?
            """

            result = conn.execute(
                query, [activity_id, start_time_s, end_time_s]
            ).fetchone()

            conn.close()

            if not result or result[-1] == 0:
                # No data found
                return {
                    "activity_id": activity_id,
                    "time_range": {
                        "start_time_s": start_time_s,
                        "end_time_s": end_time_s,
                    },
                    "statistics": {},
                    "data_points": 0,
                }

            # Parse result into statistics dict
            statistics = {}
            col_idx = 0
            for metric in metrics:
                statistics[metric] = {
                    "avg": (
                        float(result[col_idx]) if result[col_idx] is not None else 0.0
                    ),
                    "std": (
                        float(result[col_idx + 1])
                        if result[col_idx + 1] is not None
                        else 0.0
                    ),
                    "min": (
                        float(result[col_idx + 2])
                        if result[col_idx + 2] is not None
                        else 0.0
                    ),
                    "max": (
                        float(result[col_idx + 3])
                        if result[col_idx + 3] is not None
                        else 0.0
                    ),
                }
                col_idx += 4

            return {
                "activity_id": activity_id,
                "time_range": {
                    "start_time_s": start_time_s,
                    "end_time_s": end_time_s,
                },
                "statistics": statistics,
                "data_points": int(result[-1]),
            }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error querying time series statistics: {e}",
            }

    def get_time_series_raw(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get raw time series data for specified metrics and time range.

        Use this when you need actual data points (e.g., for plotting).
        For analysis, prefer get_time_series_statistics() for token efficiency.

        Args:
            activity_id: Activity ID.
            start_time_s: Start time in seconds.
            end_time_s: End time in seconds.
            metrics: List of metric column names.
            limit: Optional limit on number of rows returned.

        Returns:
            Dictionary with raw time series:
            {
                "activity_id": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "time_series": [
                    {"timestamp_s": int, "metric1": float, ...},
                    ...
                ]
            }
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            # Build SELECT clause
            select_cols = ["timestamp_s"] + metrics
            select_sql = ", ".join(select_cols)

            query = f"""
            SELECT {select_sql}
            FROM time_series_metrics
            WHERE activity_id = ?
              AND timestamp_s >= ?
              AND timestamp_s < ?
            ORDER BY timestamp_s
            """

            if limit is not None:
                query += f" LIMIT {limit}"

            results = conn.execute(
                query, [activity_id, start_time_s, end_time_s]
            ).fetchall()

            conn.close()

            # Convert to list of dicts
            time_series = []
            for row in results:
                data_point = {"timestamp_s": row[0]}
                for i, metric in enumerate(metrics):
                    data_point[metric] = row[i + 1] if row[i + 1] is not None else None
                time_series.append(data_point)

            return {
                "activity_id": activity_id,
                "time_range": {
                    "start_time_s": start_time_s,
                    "end_time_s": end_time_s,
                },
                "time_series": time_series,
            }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error querying raw time series: {e}",
            }

    def detect_anomalies_sql(
        self,
        activity_id: int,
        metrics: list[str],
        z_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """Detect anomalies using SQL-based z-score calculation.

        Calculates z-scores in DuckDB using window functions, providing
        efficient anomaly detection without loading full time series.

        Args:
            activity_id: Activity ID.
            metrics: List of metric column names to check for anomalies.
            z_threshold: Z-score threshold (default: 2.0).

        Returns:
            Dictionary with detected anomalies:
            {
                "activity_id": int,
                "anomalies": [
                    {
                        "timestamp_s": int,
                        "metric": str,
                        "value": float,
                        "z_score": float
                    },
                    ...
                ],
                "summary": {
                    "total_anomalies": int,
                    "by_metric": {metric: count, ...}
                }
            }
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)

            all_anomalies = []

            for metric in metrics:
                # Calculate z-scores using window functions
                query = f"""
                WITH stats AS (
                    SELECT
                        timestamp_s,
                        {metric} as value,
                        AVG({metric}) OVER () as mean_val,
                        STDDEV({metric}) OVER () as std_val
                    FROM time_series_metrics
                    WHERE activity_id = ?
                      AND {metric} IS NOT NULL
                )
                SELECT
                    timestamp_s,
                    value,
                    CASE
                        WHEN std_val > 0 THEN ABS((value - mean_val) / std_val)
                        ELSE 0
                    END as z_score
                FROM stats
                WHERE std_val > 0
                  AND ABS((value - mean_val) / std_val) > ?
                ORDER BY z_score DESC
                """

                results = conn.execute(query, [activity_id, z_threshold]).fetchall()

                for row in results:
                    all_anomalies.append(
                        {
                            "timestamp_s": int(row[0]),
                            "metric": metric,
                            "value": float(row[1]),
                            "z_score": float(row[2]),
                        }
                    )

            conn.close()

            # Generate summary
            by_metric: dict[str, int] = {}
            for metric in metrics:
                count = sum(1 for a in all_anomalies if a["metric"] == metric)
                by_metric[metric] = count

            summary = {"total_anomalies": len(all_anomalies), "by_metric": by_metric}

            return {
                "activity_id": activity_id,
                "anomalies": all_anomalies,
                "summary": summary,
            }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error detecting anomalies: {e}",
            }
