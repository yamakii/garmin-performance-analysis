"""Performance trend analysis for Garmin running data.

This module provides tools to analyze performance trends across multiple activities,
including linear regression analysis and filtering capabilities.
"""

import logging
from typing import Any

import numpy as np
from scipy import stats

from tools.database.db_reader import GarminDBReader

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

    # Supported metrics and their data sources
    METRIC_SOURCES = {
        "pace": "splits_pace_hr",
        "heart_rate": "splits_pace_hr",
        "cadence": "splits_all",
        "power": "splits_all",
        "vertical_oscillation": "splits_form_metrics",
        "ground_contact_time": "splits_form_metrics",
        "vertical_ratio": "splits_form_metrics",
        "distance": "activities",
        "training_effect": "activities",
        "elevation_gain": "splits_elevation",
    }

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
                "filtered_activity_ids": list[int]
            }
        """
        if metric not in self.METRIC_SOURCES:
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
                "filtered_activity_ids": filtered_ids,
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
            "filtered_activity_ids": filtered_ids,
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
        """Extract metric values from activities.

        Args:
            metric: Metric name
            activity_ids: List of activity IDs

        Returns:
            List of metric values (one per activity)
        """
        values = []

        for activity_id in activity_ids:
            value = self._get_activity_metric_average(activity_id, metric)
            if value is not None:
                values.append(value)

        # Return empty list if no valid values found
        if not values:
            return []

        return values

    def _get_activity_metric_average(
        self, activity_id: int, metric: str
    ) -> float | None:
        """Get average value of metric for an activity.

        Args:
            activity_id: Activity ID
            metric: Metric name

        Returns:
            Average metric value, or None if unavailable
        """
        source = self.METRIC_SOURCES[metric]

        if source == "splits_pace_hr":
            splits = self.db_reader.get_splits_pace_hr(activity_id)
            if not splits or not splits.get("splits"):
                return None

            if metric == "pace":
                values = [s["avg_pace_seconds_per_km"] for s in splits["splits"]]
            elif metric == "heart_rate":
                values = [
                    s["avg_heart_rate"] for s in splits["splits"] if s["avg_heart_rate"]
                ]
            else:
                return None

        elif source == "splits_form_metrics":
            splits = self.db_reader.get_splits_form_metrics(activity_id)
            if not splits or not splits.get("splits"):
                return None

            if metric == "ground_contact_time":
                values = [
                    s["ground_contact_time_ms"]
                    for s in splits["splits"]
                    if s["ground_contact_time_ms"]
                ]
            elif metric == "vertical_oscillation":
                values = [
                    s["vertical_oscillation_cm"]
                    for s in splits["splits"]
                    if s["vertical_oscillation_cm"]
                ]
            elif metric == "vertical_ratio":
                values = [
                    s["vertical_ratio_percent"]
                    for s in splits["splits"]
                    if s["vertical_ratio_percent"]
                ]
            else:
                return None

        elif source == "splits_elevation":
            splits = self.db_reader.get_splits_elevation(activity_id)
            if not splits or not splits.get("splits"):
                return None

            if metric == "elevation_gain":
                values = [
                    s["elevation_gain_m"]
                    for s in splits["splits"]
                    if s["elevation_gain_m"]
                ]
            else:
                return None

        elif source == "splits_all":
            splits = self.db_reader.get_splits_all(activity_id)
            if not splits or not splits.get("splits"):
                return None

            if metric == "cadence":
                values = [s["cadence"] for s in splits["splits"] if s["cadence"]]
            elif metric == "power":
                values = [s["power"] for s in splits["splits"] if s["power"]]
            else:
                return None

        else:
            # For activities table metrics (distance, training_effect)
            # TODO: Implement when activities table queries are available
            return None

        if not values:
            return None

        return float(np.mean(values))
