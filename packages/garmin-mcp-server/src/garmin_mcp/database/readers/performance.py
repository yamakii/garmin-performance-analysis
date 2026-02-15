"""
Performance reader for DuckDB.

Handles queries to performance_trends, activities (weather),
and section_analyses tables.
"""

import json
import logging
import warnings
from typing import Any, cast

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class PerformanceReader(BaseDBReader):
    """Reader for performance trends, weather, and section analysis data."""

    def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get performance trends data from performance_trends table.

        Args:
            activity_id: Activity ID

        Returns:
            Performance trends data with phase breakdowns.
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
            None if activity not found or weather data unavailable.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        temp_celsius,
                        relative_humidity_percent,
                        wind_speed_kmh,
                        wind_direction
                    FROM activities
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                # Convert wind speed from km/h to m/s
                wind_speed_ms = result[2] / 3.6 if result[2] else None

                # temp_celsius is already stored in Celsius, no conversion needed
                temp_c = result[0]
                # Convert Celsius to Fahrenheit
                temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None

                return {
                    "temperature_c": temp_c,
                    "temperature_f": temp_f,
                    "humidity": result[1],
                    "wind_speed_ms": wind_speed_ms,
                    "wind_direction": result[3],
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
                    "SELECT analysis_data FROM section_analyses WHERE activity_id = ? AND section_type = ? ORDER BY created_at DESC LIMIT 1",
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
