"""Performance trend analysis for Garmin running data.

This module provides tools to analyze performance trends across multiple activities,
including linear regression analysis and filtering capabilities.
"""

import logging
from typing import Any

import numpy as np
from scipy import stats

from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class PerformanceTrendAnalyzer:
    """Analyze performance trends across multiple activities.

    Supports 10 metrics: pace, HR, cadence, power, VO, GCT, VR,
    distance, training_effect, elevation_gain.

    Filtering options:
    - activity_type: Training type classification
    - temperature_range: (min_temp, max_temp) in Celsius
    - distance_range: (min_km, max_km)
    """

    # Metric name → DuckDB column name mapping
    METRIC_COLUMNS: dict[str, str] = {
        "pace": "pace_seconds_per_km",
        "heart_rate": "heart_rate",
        "cadence": "cadence",
        "power": "power",
        "vertical_oscillation": "vertical_oscillation",
        "ground_contact_time": "ground_contact_time",
        "vertical_ratio": "vertical_ratio",
        "elevation_gain": "elevation_gain",
    }

    # Metrics that are not yet supported via bulk query
    UNSUPPORTED_METRICS = {"distance", "training_effect"}

    def __init__(self, db_path: str | None = None):
        """Initialize trend analyzer.

        Args:
            db_path: Optional path to DuckDB database
        """
        self.db_reader = GarminDBReader(db_path)

    def analyze_metric_trend(
        self,
        metric: str,
        start_date: str,
        end_date: str,
        activity_ids: list[int],
        activity_type: str | None = None,
        temperature_range: tuple[float, float] | None = None,
        distance_range: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """Analyze trend for a specific metric across activities.

        Args:
            metric: Metric name (pace, heart_rate, cadence, etc.)
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            activity_ids: List of activity IDs to analyze
            activity_type: Optional activity type filter
            temperature_range: Optional (min_temp, max_temp) filter in Celsius
            distance_range: Optional (min_km, max_km) filter

        Returns:
            Dict with trend analysis:
            {
                "metric": str,
                "trend": "improving" | "declining" | "stable",
                "slope": float,
                "correlation": float,
                "p_value": float,
                "data_points": int,
                "start_date": str,
                "end_date": str,
            }
        """
        if metric not in self.METRIC_COLUMNS and metric not in self.UNSUPPORTED_METRICS:
            raise ValueError(f"Unsupported metric: {metric}")

        # Apply filters
        filtered_ids = self._apply_filters(
            activity_ids, activity_type, temperature_range, distance_range
        )

        # Extract metric values from activities
        metric_values = self._extract_metric_values(metric, filtered_ids)

        # Check if we have enough data points
        if len(metric_values) < 2:
            return {
                "metric": metric,
                "trend": "insufficient_data",
                "slope": 0.0,
                "correlation": 0.0,
                "p_value": 1.0,
                "data_points": len(metric_values),
                "start_date": start_date,
                "end_date": end_date,
            }

        # Perform linear regression
        x = np.arange(len(metric_values))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, metric_values)

        # Determine trend
        if p_value > 0.05:
            trend = "stable"
        elif slope < 0:
            # For pace, lower is better; for HR, lower can indicate efficiency
            trend = "improving" if metric == "pace" else "declining"
        else:
            trend = "declining" if metric == "pace" else "improving"

        return {
            "metric": metric,
            "trend": trend,
            "slope": float(slope),
            "correlation": float(r_value),
            "p_value": float(p_value),
            "data_points": len(metric_values),
            "start_date": start_date,
            "end_date": end_date,
        }

    def _apply_filters(
        self,
        activity_ids: list[int],
        activity_type: str | None,
        temperature_range: tuple[float, float] | None,
        distance_range: tuple[float, float] | None,
    ) -> list[int]:
        """Apply filters to activity list.

        Args:
            activity_ids: List of activity IDs
            activity_type: Optional activity type filter
            temperature_range: Optional temperature range filter
            distance_range: Optional distance range filter

        Returns:
            Filtered list of activity IDs
        """
        filtered = activity_ids.copy()

        # TODO: Implement activity_type filter using ActivityClassifier (Phase 3.3)
        if activity_type is not None:
            logger.warning("Activity type filtering not yet implemented")

        # Filter by temperature range
        if temperature_range is not None:
            min_temp, max_temp = temperature_range
            filtered = [
                aid
                for aid in filtered
                if self._check_temperature_range(aid, min_temp, max_temp)
            ]

        # Filter by distance range
        if distance_range is not None:
            min_km, max_km = distance_range
            filtered = [
                aid
                for aid in filtered
                if self._check_distance_range(aid, min_km, max_km)
            ]

        return filtered

    def _check_temperature_range(
        self, activity_id: int, min_temp: float, max_temp: float
    ) -> bool:
        """Check if activity temperature is within range.

        Args:
            activity_id: Activity ID
            min_temp: Minimum temperature in Celsius
            max_temp: Maximum temperature in Celsius

        Returns:
            True if temperature is within range, False otherwise
        """
        weather = self.db_reader.get_weather_data(activity_id)
        if not weather or weather.get("temperature_c") is None:
            return False

        temp = weather["temperature_c"]
        return bool(min_temp <= temp <= max_temp)

    def _check_distance_range(
        self, activity_id: int, min_km: float, max_km: float
    ) -> bool:
        """Check if activity distance is within range.

        Args:
            activity_id: Activity ID
            min_km: Minimum distance in km
            max_km: Maximum distance in km

        Returns:
            True if distance is within range, False otherwise
        """
        # TODO: Implement distance query from activities table
        # For now, estimate from splits
        splits = self.db_reader.get_splits_pace_hr(activity_id)
        if not splits or not splits.get("splits"):
            return False

        total_distance = sum(s.get("distance_km", 0) for s in splits["splits"])
        return bool(min_km <= total_distance <= max_km)

    def _extract_metric_values(
        self, metric: str, activity_ids: list[int]
    ) -> list[float]:
        """Extract metric values from activities using a single bulk SQL query.

        Args:
            metric: Metric name
            activity_ids: List of activity IDs

        Returns:
            List of metric values (one per activity), preserving activity_ids order
        """
        column = self.METRIC_COLUMNS.get(metric)
        if column is None:
            return []  # distance, training_effect are not yet supported

        averages = self.db_reader.get_bulk_metric_averages(activity_ids, column)
        # Preserve activity_ids order (x-axis for linear regression)
        return [averages[aid] for aid in activity_ids if aid in averages]
