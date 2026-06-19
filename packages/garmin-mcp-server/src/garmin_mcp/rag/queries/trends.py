"""Performance trend analysis for Garmin running data.

This module provides tools to analyze performance trends across multiple activities,
including linear regression analysis and filtering capabilities.
"""

import logging
from datetime import date
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
    - activity_type: NOT SUPPORTED. The ``activities`` table stores only
      running activities (filtered at ingest) and has no classification
      column, so passing ``activity_type`` raises ``NotImplementedError``
      rather than silently returning unfiltered results.
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
                "slope": float,  # change in metric per day (date-based x-axis)
                "correlation": float,
                "p_value": float,
                "data_points": int,
                "start_date": str,
                "end_date": str,
            }

        Note:
            ``slope`` is expressed **per day**: the regression x-axis is the
            number of days elapsed since the earliest activity (not the
            activity index). This corrects the previous index-based slope,
            which was sensitive to ``activity_ids`` ordering and treated
            unequal date intervals as uniform.

        Raises:
            ValueError: If ``metric`` is unsupported.
            NotImplementedError: If ``activity_type`` is provided (no
                classification column exists on the ``activities`` table).
        """
        if metric not in self.METRIC_COLUMNS and metric not in self.UNSUPPORTED_METRICS:
            raise ValueError(f"Unsupported metric: {metric}")

        # Apply filters
        filtered_ids = self._apply_filters(
            activity_ids, activity_type, temperature_range, distance_range
        )

        # Extract metric values keyed by activity_id.
        metric_values_by_id = self._extract_metric_values(metric, filtered_ids)

        # Pair each value with its activity date and sort chronologically so
        # the regression x-axis reflects real elapsed time, not call order.
        date_value_pairs = self._build_date_value_pairs(metric_values_by_id)

        # Check if we have enough data points
        if len(date_value_pairs) < 2:
            return {
                "metric": metric,
                "trend": "insufficient_data",
                "slope": 0.0,
                "correlation": 0.0,
                "p_value": 1.0,
                "data_points": len(date_value_pairs),
                "start_date": start_date,
                "end_date": end_date,
            }

        # Build a date-based x-axis: days elapsed since the earliest activity.
        ordinals = [d.toordinal() for d, _ in date_value_pairs]
        base = ordinals[0]
        x = np.array([o - base for o in ordinals], dtype=float)
        metric_values = [v for _, v in date_value_pairs]
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
            "data_points": len(date_value_pairs),
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

        Raises:
            NotImplementedError: If ``activity_type`` is provided. The
                ``activities`` table has no classification column (only
                running activities are ingested), so we refuse to silently
                return unfiltered results.
        """
        if activity_type is not None:
            raise NotImplementedError(
                "activity_type filtering is not supported: the activities "
                "table has no classification column (only running activities "
                "are ingested). Remove the activity_type argument."
            )

        filtered = activity_ids.copy()

        if temperature_range is None and distance_range is None:
            return filtered

        # Bulk-fetch the fields needed for any active filter in one query,
        # avoiding the previous per-activity (N+1) reader calls.
        needed_fields: list[str] = []
        if temperature_range is not None:
            needed_fields.append("temp_celsius")
        if distance_range is not None:
            needed_fields.append("total_distance_km")

        fields_by_id = self.db_reader.get_bulk_activity_fields(filtered, needed_fields)

        result: list[int] = []
        for aid in filtered:
            fields = fields_by_id.get(aid)
            if fields is None:
                continue

            if temperature_range is not None:
                min_temp, max_temp = temperature_range
                temp = fields.get("temp_celsius")
                if temp is None or not (min_temp <= temp <= max_temp):
                    continue

            if distance_range is not None:
                min_km, max_km = distance_range
                distance = fields.get("total_distance_km")
                if distance is None or not (min_km <= distance <= max_km):
                    continue

            result.append(aid)

        return result

    def _extract_metric_values(
        self, metric: str, activity_ids: list[int]
    ) -> dict[int, float]:
        """Extract metric values from activities using a single bulk SQL query.

        Args:
            metric: Metric name
            activity_ids: List of activity IDs

        Returns:
            Dict mapping activity_id -> average metric value. Activities with
            no data are omitted.
        """
        column = self.METRIC_COLUMNS.get(metric)
        if column is None:
            return {}  # distance, training_effect are not yet supported

        return self.db_reader.get_bulk_metric_averages(activity_ids, column)

    def _build_date_value_pairs(
        self, metric_values_by_id: dict[int, float]
    ) -> list[tuple[date, float]]:
        """Pair metric values with activity dates, sorted chronologically.

        Args:
            metric_values_by_id: Mapping of activity_id -> metric value

        Returns:
            List of (activity_date, value) tuples sorted by date ascending.
            Activities without a parseable date are dropped.
        """
        if not metric_values_by_id:
            return []

        dates_by_id = self.db_reader.get_activity_dates(
            list(metric_values_by_id.keys())
        )

        pairs: list[tuple[date, float]] = []
        for aid, value in metric_values_by_id.items():
            date_str = dates_by_id.get(aid)
            if date_str is None:
                continue
            try:
                activity_date = date.fromisoformat(str(date_str)[:10])
            except ValueError:
                logger.warning(
                    "Skipping activity %s: unparseable date %r", aid, date_str
                )
                continue
            pairs.append((activity_date, value))

        pairs.sort(key=lambda p: p[0])
        return pairs
