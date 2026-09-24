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

    Supports 8 metrics: pace, heart_rate, cadence, power, vertical_oscillation,
    ground_contact_time, vertical_ratio, elevation_gain.

    Trend labels depend on the metric:
    - Lower is better (pace, ground_contact_time, vertical_oscillation,
      vertical_ratio): a significant fall is ``improving``, a rise ``declining``.
    - Neutral (heart_rate, power, cadence, elevation_gain): these are not
      comparable across runs at different paces, so a significant change is
      only described as ``increasing`` / ``decreasing``.

    Filtering options:
    - start_date / end_date: activities dated outside the window are dropped
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

    # Metrics where a falling value means better running economy / speed.
    LOWER_IS_BETTER_METRICS = frozenset(
        {"pace", "ground_contact_time", "vertical_oscillation", "vertical_ratio"}
    )

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
        activity_ids: list[int] | None = None,
        temperature_range: tuple[float, float] | None = None,
        distance_range: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """Analyze trend for a specific metric across activities.

        Args:
            metric: Metric name (pace, heart_rate, cadence, etc.)
            start_date: Inclusive start date in YYYY-MM-DD format; activities
                dated earlier are dropped
            end_date: Inclusive end date in YYYY-MM-DD format; activities dated
                later are dropped
            activity_ids: Activities to analyze; None uses every activity dated
                in the window
            temperature_range: Optional (min_temp, max_temp) filter in Celsius
            distance_range: Optional (min_km, max_km) filter

        Returns:
            Dict with trend analysis:
            {
                "metric": str,
                "trend": "improving" | "declining" (lower-is-better metrics)
                         | "increasing" | "decreasing" (neutral metrics)
                         | "stable" | "insufficient_data",
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
            ValueError: If ``metric`` is unsupported (the message lists the
                supported metrics) or a date bound is not YYYY-MM-DD.
        """
        self._check_metric(metric)
        window_start = date.fromisoformat(start_date)
        window_end = date.fromisoformat(end_date)

        if activity_ids is None:
            activity_ids = self.db_reader.get_activity_ids_between(start_date, end_date)

        # Apply filters
        filtered_ids = self._apply_filters(
            activity_ids, temperature_range, distance_range
        )

        # Extract metric values keyed by activity_id.
        metric_values_by_id = self._extract_metric_values(metric, filtered_ids)

        # Pair each value with its activity date and sort chronologically so
        # the regression x-axis reflects real elapsed time, not call order.
        # Activities dated outside [start_date, end_date] are dropped.
        date_value_pairs = [
            (d, v)
            for d, v in self._build_date_value_pairs(metric_values_by_id)
            if window_start <= d <= window_end
        ]

        # Check if we have enough data points. Require at least 3: with exactly
        # 2 points scipy.stats.linregress returns p_value == nan (df=0), and
        # ``nan > 0.05`` is False, so a 2-point regression would bypass the
        # significance gate below and confidently classify a direction.
        if len(date_value_pairs) < 3:
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

        return {
            "metric": metric,
            "trend": self._classify_trend(metric, float(slope), float(p_value)),
            "slope": float(slope),
            "correlation": float(r_value),
            "p_value": float(p_value),
            "data_points": len(date_value_pairs),
            "start_date": start_date,
            "end_date": end_date,
        }

    def summarize_metric_period(
        self,
        metric: str,
        activity_ids: list[int],
        prev_activity_ids: list[int],
    ) -> dict[str, Any]:
        """Descriptive period summary of a metric (no within-period regression).

        At week granularity, N (typically 3-6 runs) cannot support a linear
        regression, and any signal is confounded by the week's workout-type mix
        rather than fitness (Issue #813). Instead of regressing, describe the
        period with its median and position it against the previous period's
        median.

        Args:
            metric: Metric name (pace, heart_rate, ...).
            activity_ids: Activity IDs inside the current period.
            prev_activity_ids: Activity IDs inside the immediately preceding
                period (e.g. the prior week), used for the period-over-period
                delta.

        Returns:
            Dict::

                {
                    "metric": str,
                    "mode": "descriptive",
                    "median": float | None,        # None when no data
                    "prev_period_median": float | None,
                    "delta_pct": float | None,     # None when either median is None
                    "data_points": int,
                    "prev_data_points": int,
                }

            Deliberately carries no ``trend`` / ``slope`` / ``p_value`` keys:
            there is no regression at this granularity.

        Raises:
            ValueError: If ``metric`` is unsupported.
        """
        self._check_metric(metric)

        current = list(self._extract_metric_values(metric, activity_ids).values())
        previous = list(self._extract_metric_values(metric, prev_activity_ids).values())

        median = float(np.median(current)) if current else None
        prev_median = float(np.median(previous)) if previous else None

        delta_pct: float | None = None
        if median is not None and prev_median is not None and prev_median != 0:
            delta_pct = (median - prev_median) / prev_median * 100.0

        return {
            "metric": metric,
            "mode": "descriptive",
            "median": median,
            "prev_period_median": prev_median,
            "delta_pct": delta_pct,
            "data_points": len(current),
            "prev_data_points": len(previous),
        }

    def _check_metric(self, metric: str) -> None:
        """Raise ``ValueError`` listing the supported metrics if ``metric`` is not one."""
        if metric not in self.METRIC_COLUMNS:
            supported = ", ".join(self.METRIC_COLUMNS)
            raise ValueError(
                f"Unsupported metric: {metric}. Supported metrics: {supported}"
            )

    def _classify_trend(self, metric: str, slope: float, p_value: float) -> str:
        """Label a fitted slope.

        Lower-is-better metrics get ``improving`` / ``declining``; the others are
        not comparable across runs at different paces, so they only get the
        neutral ``increasing`` / ``decreasing``. A non-significant (or
        undefined) p-value is ``stable``.
        """
        if not p_value <= 0.05:
            return "stable"
        if metric in self.LOWER_IS_BETTER_METRICS:
            return "improving" if slope < 0 else "declining"
        return "decreasing" if slope < 0 else "increasing"

    def _apply_filters(
        self,
        activity_ids: list[int],
        temperature_range: tuple[float, float] | None,
        distance_range: tuple[float, float] | None,
    ) -> list[int]:
        """Apply filters to activity list.

        Args:
            activity_ids: List of activity IDs
            temperature_range: Optional temperature range filter
            distance_range: Optional distance range filter

        Returns:
            Filtered list of activity IDs
        """
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
        column = self.METRIC_COLUMNS[metric]
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
