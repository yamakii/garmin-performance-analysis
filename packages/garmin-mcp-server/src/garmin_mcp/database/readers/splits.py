"""
Splits reader for lap-by-lap performance data.

Handles all splits table queries with optional statistics-only mode.
"""

import logging
from typing import Any

from garmin_mcp.database.readers import splits_query_builder as qb
from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class SplitsReader(BaseDBReader):
    """Reader for splits data queries."""

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
                Dict with aggregated statistics
        """
        try:
            with self._get_connection() as conn:
                if statistics_only:
                    sql = qb.build_statistics_sql(qb.PACE_HR_FIELDS)
                    result = conn.execute(sql, [activity_id]).fetchone()
                    return qb.parse_statistics_result(
                        result, qb.PACE_HR_FIELDS, activity_id
                    )

                sql = qb.build_full_sql(qb.PACE_HR_FULL_COLUMNS)
                rows = conn.execute(sql, [activity_id]).fetchall()
                return qb.parse_full_result(rows, qb.PACE_HR_FULL_KEYS)

        except Exception as e:
            logger.error(f"Error getting splits pace/HR data: {e}")
            if statistics_only:
                return qb.empty_stats_result(activity_id)
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
                Dict with aggregated statistics
        """
        try:
            with self._get_connection() as conn:
                if statistics_only:
                    sql = qb.build_statistics_sql(qb.FORM_FIELDS)
                    result = conn.execute(sql, [activity_id]).fetchone()
                    return qb.parse_statistics_result(
                        result, qb.FORM_FIELDS, activity_id
                    )

                sql = qb.build_full_sql(qb.FORM_FULL_COLUMNS)
                rows = conn.execute(sql, [activity_id]).fetchall()
                return qb.parse_full_result(rows, qb.FORM_FULL_KEYS)

        except Exception as e:
            logger.error(f"Error getting splits form metrics: {e}")
            if statistics_only:
                return qb.empty_stats_result(activity_id)
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
                Dict with aggregated statistics
        """
        try:
            with self._get_connection() as conn:
                if statistics_only:
                    sql = qb.build_statistics_sql(qb.ELEVATION_FIELDS)
                    result = conn.execute(sql, [activity_id]).fetchone()
                    return qb.parse_statistics_result(
                        result, qb.ELEVATION_FIELDS, activity_id
                    )

                sql = qb.build_full_sql(qb.ELEVATION_FULL_COLUMNS)
                rows = conn.execute(sql, [activity_id]).fetchall()
                return qb.parse_full_result(
                    rows,
                    qb.ELEVATION_FULL_KEYS,
                    extra_keys=qb.ELEVATION_EXTRA_KEYS,
                )

        except Exception as e:
            logger.error(f"Error getting splits elevation data: {e}")
            if statistics_only:
                return qb.empty_stats_result(activity_id)
            return {"splits": []}

    def get_splits_comprehensive(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """
        Get comprehensive split data (14 fields) from splits table.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                           instead of per-split data. Significantly reduces output size (~80% reduction).
                           Default: False (backward compatible)

        Returns:
            Full mode (statistics_only=False):
                Dict with 'splits' key containing list of split data with all 14 fields
            Statistics mode (statistics_only=True):
                Dict with aggregated statistics for 12 numeric fields
        """
        try:
            with self._get_connection() as conn:
                if statistics_only:
                    sql = qb.build_statistics_sql(qb.COMPREHENSIVE_STAT_FIELDS)
                    result = conn.execute(sql, [activity_id]).fetchone()
                    return qb.parse_statistics_result(
                        result, qb.COMPREHENSIVE_STAT_FIELDS, activity_id
                    )

                sql = qb.build_full_sql(qb.COMPREHENSIVE_FULL_COLUMNS)
                rows = conn.execute(sql, [activity_id]).fetchall()
                return qb.parse_full_result(
                    rows,
                    qb.COMPREHENSIVE_FULL_KEYS,
                    defaults=qb.COMPREHENSIVE_FULL_DEFAULTS,
                )

        except Exception as e:
            logger.error(f"Error getting comprehensive splits data: {e}")
            if statistics_only:
                return qb.empty_stats_result(activity_id)
            return {"splits": []}

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
        import json
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
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
