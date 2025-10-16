"""
Splits reader for lap-by-lap performance data.

Handles all splits table queries with optional statistics-only mode.
"""

import logging
from typing import Any

from tools.database.readers.base import BaseDBReader

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
            with self._get_connection() as conn:
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
                                "mean": (
                                    float(result[0]) if result[0] is not None else 0.0
                                ),
                                "median": (
                                    float(result[1]) if result[1] is not None else 0.0
                                ),
                                "std": (
                                    float(result[2]) if result[2] is not None else 0.0
                                ),
                                "min": (
                                    float(result[3]) if result[3] is not None else 0.0
                                ),
                                "max": (
                                    float(result[4]) if result[4] is not None else 0.0
                                ),
                            },
                            "heart_rate": {
                                "mean": (
                                    float(result[5]) if result[5] is not None else 0.0
                                ),
                                "median": (
                                    float(result[6]) if result[6] is not None else 0.0
                                ),
                                "std": (
                                    float(result[7]) if result[7] is not None else 0.0
                                ),
                                "min": (
                                    float(result[8]) if result[8] is not None else 0.0
                                ),
                                "max": (
                                    float(result[9]) if result[9] is not None else 0.0
                                ),
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
            with self._get_connection() as conn:
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
                                "mean": (
                                    float(result[0]) if result[0] is not None else 0.0
                                ),
                                "median": (
                                    float(result[1]) if result[1] is not None else 0.0
                                ),
                                "std": (
                                    float(result[2]) if result[2] is not None else 0.0
                                ),
                                "min": (
                                    float(result[3]) if result[3] is not None else 0.0
                                ),
                                "max": (
                                    float(result[4]) if result[4] is not None else 0.0
                                ),
                            },
                            "vertical_oscillation": {
                                "mean": (
                                    float(result[5]) if result[5] is not None else 0.0
                                ),
                                "median": (
                                    float(result[6]) if result[6] is not None else 0.0
                                ),
                                "std": (
                                    float(result[7]) if result[7] is not None else 0.0
                                ),
                                "min": (
                                    float(result[8]) if result[8] is not None else 0.0
                                ),
                                "max": (
                                    float(result[9]) if result[9] is not None else 0.0
                                ),
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
            with self._get_connection() as conn:
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
                                "mean": (
                                    float(result[0]) if result[0] is not None else 0.0
                                ),
                                "median": (
                                    float(result[1]) if result[1] is not None else 0.0
                                ),
                                "std": (
                                    float(result[2]) if result[2] is not None else 0.0
                                ),
                                "min": (
                                    float(result[3]) if result[3] is not None else 0.0
                                ),
                                "max": (
                                    float(result[4]) if result[4] is not None else 0.0
                                ),
                            },
                            "elevation_loss": {
                                "mean": (
                                    float(result[5]) if result[5] is not None else 0.0
                                ),
                                "median": (
                                    float(result[6]) if result[6] is not None else 0.0
                                ),
                                "std": (
                                    float(result[7]) if result[7] is not None else 0.0
                                ),
                                "min": (
                                    float(result[8]) if result[8] is not None else 0.0
                                ),
                                "max": (
                                    float(result[9]) if result[9] is not None else 0.0
                                ),
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
