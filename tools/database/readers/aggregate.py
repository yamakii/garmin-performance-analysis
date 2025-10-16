"""
Aggregate reader for pre-computed performance metrics.

Handles queries to aggregate tables: form_efficiency, hr_efficiency,
heart_rate_zones, vo2_max, lactate_threshold, performance_trends,
and section_analyses.
"""

import json
import logging
import warnings
from typing import Any, cast

from tools.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class AggregateReader(BaseDBReader):
    """Reader for aggregate performance metrics."""

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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
        # Show deprecation warning
        warnings.warn(
            "get_section_analysis() may return large amounts of data. "
            "Consider using extract_insights() MCP function for "
            "keyword-based summarized insights instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT analysis_data FROM section_analyses WHERE activity_id = ? AND section_type = ?",
                    [activity_id, section_type],
                ).fetchone()

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
