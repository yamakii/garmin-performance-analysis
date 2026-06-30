"""Form anomaly detection with cause analysis.

This module provides functionality to detect anomalies in form metrics (GCT, VO, VR)
and analyze their probable causes (elevation change, pace change, fatigue).

Key features:
- Z-score based anomaly detection
- Rolling statistics calculation (60-second window)
- Cause classification (elevation, pace, fatigue)
- Context window extraction (before/after anomaly)
- Correlation analysis for cause confidence
- Recommendation generation
"""

import statistics
from pathlib import Path
from typing import Any

from garmin_mcp.rag.loaders.activity_details_loader import ActivityDetailsLoader

# Default z-score threshold for anomaly detection.
# Raised from 2.0 to 3.0 to avoid flagging small, materially-insignificant
# fluctuations (especially VO, whose 60s-window std is only ~0.1-0.2 cm).
DEFAULT_Z_THRESHOLD = 3.0

# Minimum absolute deviation from the rolling mean for an anomaly to be
# considered material (combined with the z-score threshold via AND).
# Values are aligned with the form_degradation_triggers contract:
#   VO  >= 0.5 cm, GCT >= 10 ms, VR >= 0.3 %.
# Metrics not listed here (cadence, power, pace, ...) have no magnitude gate.
MAGNITUDE_GATES: dict[str, float] = {
    "directVerticalOscillation": 0.5,  # cm
    "directGroundContactTime": 10.0,  # ms
    "directVerticalRatio": 0.3,  # %
}

# Sustained degradation thresholds: a form metric is considered to be in a
# persistent fatigue-driven decline when its second-half rolling mean exceeds
# its first-half rolling mean by at least this amount (same units as the
# magnitude gates / form_degradation_triggers).
FORM_DEGRADATION_TRIGGERS: dict[str, float] = {
    "directVerticalOscillation": 0.5,  # cm
    "directGroundContactTime": 10.0,  # ms
    "directVerticalRatio": 0.3,  # %
}

# Japanese display labels for the form metrics, used to name the dominant metric
# in generated recommendations instead of hard-coding a single metric (#666).
METRIC_LABELS: dict[str, str] = {
    "directGroundContactTime": "接地時間(GCT)",
    "directVerticalOscillation": "上下動(VO)",
    "directVerticalRatio": "上下動比(VR)",
}


class FormAnomalyDetector:
    """Detect form metric anomalies and identify probable causes.

    This class provides methods to:
    - Detect anomalies using z-score analysis
    - Calculate rolling statistics for baseline comparison
    - Classify anomaly causes (elevation, pace, fatigue)
    - Extract context windows around anomalies
    - Generate improvement recommendations

    Attributes:
        base_path: Base directory path for data files
        loader: ActivityDetailsLoader instance for loading activity data
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize FormAnomalyDetector.

        Args:
            base_path: Base directory path for data files.
                      Defaults to GARMIN_DATA_DIR from environment if not provided.
        """
        if base_path is None:
            from garmin_mcp.utils.paths import get_data_base_dir

            base_path = get_data_base_dir()
        self.base_path = base_path
        self.loader = ActivityDetailsLoader(base_path=self.base_path)

    def _calculate_rolling_stats(
        self,
        time_series: list[float | None],
        window_size: int = 60,
    ) -> tuple[list[float], list[float]]:
        """Calculate rolling mean and standard deviation.

        Args:
            time_series: List of metric values.
            window_size: Rolling window size in seconds (default: 60).

        Returns:
            Tuple of (rolling_means, rolling_stds).
        """
        rolling_means = []
        rolling_stds = []

        for i in range(len(time_series)):
            # Define window boundaries
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(time_series), i + window_size // 2)

            # Get window values (filter None)
            window_values = [v for v in time_series[start_idx:end_idx] if v is not None]

            if len(window_values) >= 2:
                rolling_means.append(statistics.mean(window_values))
                rolling_stds.append(statistics.stdev(window_values))
            else:
                rolling_means.append(0.0)
                rolling_stds.append(0.0)

        return rolling_means, rolling_stds

    def _has_sustained_degradation(
        self,
        metric_name: str,
        metric_series: list[float | None],
    ) -> bool:
        """Determine whether a form metric shows a sustained degradation trend.

        Compares the mean of the second half of the activity to the first half.
        Returns True only when the increase (worsening) exceeds the metric's
        ``form_degradation_trigger``. Metrics without a configured trigger and
        series too short to split return False.

        Args:
            metric_name: Name of the form metric.
            metric_series: Time series of the form metric values.

        Returns:
            True if a persistent first-half vs second-half degradation exceeding
            the form_degradation_trigger exists, else False.
        """
        trigger = FORM_DEGRADATION_TRIGGERS.get(metric_name)
        if trigger is None:
            return False

        values = [v for v in metric_series if v is not None]
        if len(values) < 4:
            return False

        midpoint = len(values) // 2
        first_half = values[:midpoint]
        second_half = values[midpoint:]
        if not first_half or not second_half:
            return False

        return (statistics.mean(second_half) - statistics.mean(first_half)) >= trigger

    def _detect_anomalies_by_zscore(
        self,
        metric_name: str,
        time_series: list[float | None],
        rolling_means: list[float],
        rolling_stds: list[float],
        z_threshold: float = DEFAULT_Z_THRESHOLD,
    ) -> list[dict[str, Any]]:
        """Detect anomalies using z-score method with rolling statistics.

        An anomaly is flagged only when **both** conditions hold:
        - the z-score exceeds ``z_threshold`` AND
        - the absolute deviation from the rolling mean is at least the metric's
          magnitude gate (``MAGNITUDE_GATES``). Metrics without a configured
          gate use the z-score condition alone.

        This combined gate prevents small, materially-insignificant fluctuations
        (e.g. a few mm of vertical oscillation) from being reported as anomalies.

        Args:
            metric_name: Name of the metric being analyzed.
            time_series: List of metric values.
            rolling_means: List of rolling mean values.
            rolling_stds: List of rolling standard deviation values.
            z_threshold: Z-score threshold for anomaly detection (default: 3.0).

        Returns:
            List of anomaly dictionaries with timestamp, value, z-score.
        """
        anomalies = []
        magnitude_gate = MAGNITUDE_GATES.get(metric_name)

        for idx, value in enumerate(time_series):
            if value is None:
                continue

            mean_val = rolling_means[idx]
            std_val = rolling_stds[idx]

            if std_val == 0:
                continue

            deviation = abs(value - mean_val)
            z_score = deviation / std_val

            if z_score <= z_threshold:
                continue

            # Absolute-change gate: skip sub-threshold magnitude changes.
            if magnitude_gate is not None and deviation < magnitude_gate:
                continue

            anomalies.append(
                {
                    "timestamp": idx,
                    "metric": metric_name,
                    "value": value,
                    "baseline": mean_val,
                    "z_score": z_score,
                }
            )

        return anomalies

    def _analyze_anomaly_causes(
        self,
        anomaly: dict[str, Any],
        elevation_series: list[float | None],
        pace_series: list[float | None],
        hr_series: list[float | None],
        sustained_degradation: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """Analyze probable cause of anomaly using correlation analysis.

        ``fatigue`` is assigned only when the metric exhibits a *sustained*
        degradation trend across the activity (``sustained_degradation=True``).
        Isolated/sporadic point anomalies — even when accumulated HR drift is
        high — are classified as ``isolated`` (no fabricated correlation)
        instead, to avoid labelling natural late-activity HR drift as
        fatigue-driven form breakdown *and* to avoid inflating ``pace_change``
        with anomalies that have no real pace signal (#666).

        Args:
            anomaly: Anomaly dictionary with timestamp and metric info.
            elevation_series: Elevation time series.
            pace_series: Pace time series (min/km).
            hr_series: Heart rate time series.
            sustained_degradation: Whether the metric for this anomaly shows a
                persistent first-half vs second-half degradation exceeding its
                form_degradation_trigger. Required for a ``fatigue`` label.

        Returns:
            Tuple of (probable_cause, cause_details).
            Probable causes: "elevation_change", "pace_change", "fatigue",
            "isolated" (no identifiable cause).
        """
        timestamp = anomaly["timestamp"]

        # Calculate changes in contextual metrics
        # Elevation change (5 seconds window)
        elev_start = max(0, timestamp - 5)
        elev_end = min(len(elevation_series), timestamp + 5)
        elev_values = [
            e for e in elevation_series[elev_start:elev_end] if e is not None
        ]
        elevation_change = (
            max(elev_values) - min(elev_values) if len(elev_values) > 1 else 0.0
        )

        # Pace change (10 seconds window)
        pace_start = max(0, timestamp - 10)
        pace_end = min(len(pace_series), timestamp + 10)
        pace_values = [p for p in pace_series[pace_start:pace_end] if p is not None]
        pace_change = (
            max(pace_values) - min(pace_values) if len(pace_values) > 1 else 0.0
        )

        # HR drift (calculate from start to this point)
        hr_baseline_end = min(300, len(hr_series))  # First 5 minutes
        hr_baseline = [h for h in hr_series[:hr_baseline_end] if h is not None]
        hr_current_start = max(0, timestamp - 60)
        hr_current = [h for h in hr_series[hr_current_start:timestamp] if h is not None]

        hr_drift_percent = 0.0
        if len(hr_baseline) > 0 and len(hr_current) > 0:
            baseline_avg = statistics.mean(hr_baseline)
            current_avg = statistics.mean(hr_current)
            hr_drift_percent = ((current_avg - baseline_avg) / baseline_avg) * 100

        # Classify cause based on thresholds
        cause_details = {
            "elevation_change_5s": elevation_change,
            "pace_change_10s": pace_change,
            "hr_drift_percent": hr_drift_percent,
        }

        # Priority: elevation > pace > fatigue
        if elevation_change > 5.0:
            # Calculate correlation (simplified as presence of change)
            cause_details["elevation_correlation"] = min(
                0.95, 0.5 + (elevation_change / 20.0)
            )
            return "elevation_change", cause_details
        elif pace_change > 0.25:  # ~15 sec/km change
            cause_details["pace_correlation"] = min(0.95, 0.5 + (pace_change / 0.5))
            return "pace_change", cause_details
        elif abs(hr_drift_percent) > 10.0 and sustained_degradation:
            # Fatigue requires BOTH significant HR drift AND a persistent
            # degradation trend in the form metric. High HR drift alone (which
            # naturally occurs late in a run) is not sufficient.
            cause_details["hr_correlation"] = min(
                0.95, 0.5 + (abs(hr_drift_percent) / 30.0)
            )
            return "fatigue", cause_details
        else:
            # Isolated / sporadic point anomaly: no elevation, pace, or
            # sustained fatigue signal. Do not fabricate a pace correlation —
            # these were previously mis-labelled as low-confidence pace_change
            # and inflated the "ペース急変→VO増加" recommendation (#666).
            return "isolated", cause_details

    def _extract_context(
        self,
        timestamp: int,
        metric_series: list[float | None],
        elevation_series: list[float | None],
        window: int = 30,
    ) -> dict[str, dict[str, float]]:
        """Extract before/after context around anomaly timestamp.

        Args:
            timestamp: Anomaly timestamp.
            metric_series: Form metric time series (GCT, VO, VR).
            elevation_series: Elevation time series.
            window: Context window size in seconds (default: 30).

        Returns:
            Dictionary with before_30s and after_30s context:
            {
                "before_30s": {"metric_avg": float, "elevation": float},
                "after_30s": {"metric_avg": float, "elevation": float}
            }
        """
        # Before window
        before_start = max(0, timestamp - window)
        before_values = [
            v for v in metric_series[before_start:timestamp] if v is not None
        ]
        before_elev = [
            e for e in elevation_series[before_start:timestamp] if e is not None
        ]

        before_ctx = {
            "metric_avg": (
                statistics.mean(before_values) if len(before_values) > 0 else 0.0
            ),
            "elevation": statistics.mean(before_elev) if len(before_elev) > 0 else 0.0,
        }

        # After window
        after_end = min(len(metric_series), timestamp + window)
        after_values = [v for v in metric_series[timestamp:after_end] if v is not None]
        after_elev = [e for e in elevation_series[timestamp:after_end] if e is not None]

        after_ctx = {
            "metric_avg": (
                statistics.mean(after_values) if len(after_values) > 0 else 0.0
            ),
            "elevation": statistics.mean(after_elev) if len(after_elev) > 0 else 0.0,
        }

        return {"before_30s": before_ctx, "after_30s": after_ctx}

    def _generate_recommendations(self, anomalies: list[dict[str, Any]]) -> list[str]:
        """Generate improvement recommendations from cause-classified anomalies.

        For each identifiable cause (elevation/pace/fatigue) the dominant form
        metric driving that cause is named explicitly, instead of hard-coding a
        single metric (the previous version always said "VO増加" regardless of
        which metric actually spiked, #666). Anomalies whose cause is
        ``isolated`` (no identifiable trigger) produce no recommendation, so a
        run with only isolated noise yields an empty list.

        Args:
            anomalies: List of anomaly records, each with ``probable_cause`` and
                ``metric`` keys.

        Returns:
            List of recommendation strings (empty when no cause-identified
            anomalies exist).
        """
        from collections import Counter

        cause_templates = {
            "elevation_change": "上り坂で{label}悪化 → 上り坂練習を強化",
            "pace_change": "ペース変化時に{label}が増加 → ペース変化を緩やかに",
            "fatigue": "後半に{label}悪化（疲労傾向）→ 持久力トレーニング強化",
        }

        recommendations: list[str] = []
        for cause, template in cause_templates.items():
            metrics = [
                a["metric"] for a in anomalies if a.get("probable_cause") == cause
            ]
            if not metrics:
                continue
            dominant_metric = Counter(metrics).most_common(1)[0][0]
            label = METRIC_LABELS.get(dominant_metric, dominant_metric)
            recommendations.append(template.format(label=label))

        return recommendations

    def _extract_time_series(
        self,
        activity_id: int,
        metrics: list[str] | None = None,
    ) -> tuple[
        dict[str, Any], dict[str, list[float | None]], dict[str, list[float | None]]
    ]:
        """Extract time series data for form metrics and contextual metrics.

        Args:
            activity_id: Activity ID.
            metrics: List of form metric names to analyze.

        Returns:
            Tuple of:
            - metric_map: Metric descriptor map
            - form_metrics: Dict of form metric time series
            - context_metrics: Dict with elevation, pace, hr time series
        """
        # Default metrics if not specified
        if metrics is None:
            metrics = [
                "directGroundContactTime",
                "directVerticalOscillation",
                "directVerticalRatio",
            ]

        # Load activity_details.json
        activity_details = self.loader.load_activity_details(activity_id)

        # Parse metric descriptors
        metric_map = self.loader.parse_metric_descriptors(
            activity_details["metricDescriptors"]
        )

        # Extract time series for form metrics
        metrics_data = activity_details["activityDetailMetrics"]

        # Initialize storage
        form_metrics: dict[str, list[float | None]] = {m: [] for m in metrics}
        elevation_series: list[float | None] = []
        pace_series: list[float | None] = []
        hr_series: list[float | None] = []

        # Extract all time series
        for measurement in metrics_data:
            values = measurement["metrics"]

            # Extract form metrics
            for metric_name in metrics:
                if metric_name in metric_map:
                    metric_info = metric_map[metric_name]
                    metric_idx = metric_info["index"]
                    if metric_idx < len(values):
                        raw_val = values[metric_idx]
                        if raw_val is not None:
                            converted_val = self.loader.apply_unit_conversion(
                                metric_info, raw_val
                            )
                            form_metrics[metric_name].append(converted_val)
                        else:
                            form_metrics[metric_name].append(None)
                    else:
                        form_metrics[metric_name].append(None)

            # Elevation
            if "directElevation" in metric_map:
                elev_idx = metric_map["directElevation"]["index"]
                elev_val = values[elev_idx] if elev_idx < len(values) else None
                if elev_val is not None:
                    elev_val = self.loader.apply_unit_conversion(
                        metric_map["directElevation"], elev_val
                    )
                elevation_series.append(elev_val)
            else:
                elevation_series.append(None)

            # Pace (from speed)
            if "directSpeed" in metric_map:
                speed_idx = metric_map["directSpeed"]["index"]
                speed_val = values[speed_idx] if speed_idx < len(values) else None
                if speed_val is not None:
                    speed_val = self.loader.apply_unit_conversion(
                        metric_map["directSpeed"], speed_val
                    )
                    # Convert m/s to min/km
                    pace_val = (1000.0 / speed_val) / 60.0 if speed_val > 0 else None
                    pace_series.append(pace_val)
                else:
                    pace_series.append(None)
            else:
                pace_series.append(None)

            # Heart rate
            if "directHeartRate" in metric_map:
                hr_idx = metric_map["directHeartRate"]["index"]
                hr_val = values[hr_idx] if hr_idx < len(values) else None
                if hr_val is not None:
                    hr_val = self.loader.apply_unit_conversion(
                        metric_map["directHeartRate"], hr_val
                    )
                hr_series.append(hr_val)
            else:
                hr_series.append(None)

        context_metrics = {
            "elevation": elevation_series,
            "pace": pace_series,
            "hr": hr_series,
        }

        return metric_map, form_metrics, context_metrics

    def _detect_all_anomalies(
        self,
        form_metrics: dict[str, list[float | None]],
        elevation_series: list[float | None],
        pace_series: list[float | None],
        hr_series: list[float | None],
        z_threshold: float = DEFAULT_Z_THRESHOLD,
        context_window: int = 30,
    ) -> list[dict[str, Any]]:
        """Detect anomalies for all form metrics.

        Args:
            form_metrics: Dict of form metric time series.
            elevation_series: Elevation time series.
            pace_series: Pace time series.
            hr_series: Heart rate time series.
            z_threshold: Z-score threshold.
            context_window: Context window size in seconds.

        Returns:
            List of anomaly records with full details.
        """
        all_anomalies = []
        anomaly_counter = 1

        for metric_name, metric_series in form_metrics.items():
            if not metric_series:
                continue

            # Calculate rolling statistics
            rolling_means, rolling_stds = self._calculate_rolling_stats(
                metric_series, window_size=60
            )

            # Pre-compute whether this metric shows a sustained degradation
            # trend (required for a fatigue classification).
            sustained_degradation = self._has_sustained_degradation(
                metric_name, metric_series
            )

            # Detect anomalies
            raw_anomalies = self._detect_anomalies_by_zscore(
                metric_name,
                metric_series,
                rolling_means,
                rolling_stds,
                z_threshold,
            )

            # Analyze causes and add context
            for raw_anomaly in raw_anomalies:
                probable_cause, cause_details = self._analyze_anomaly_causes(
                    raw_anomaly,
                    elevation_series,
                    pace_series,
                    hr_series,
                    sustained_degradation,
                )

                context = self._extract_context(
                    raw_anomaly["timestamp"],
                    metric_series,
                    elevation_series,
                    context_window,
                )

                anomaly_record = {
                    "anomaly_id": anomaly_counter,
                    "timestamp": raw_anomaly["timestamp"],
                    "metric": raw_anomaly["metric"],
                    "value": raw_anomaly["value"],
                    "baseline": raw_anomaly["baseline"],
                    "z_score": raw_anomaly["z_score"],
                    "probable_cause": probable_cause,
                    "cause_details": cause_details,
                    "context": context,
                }

                all_anomalies.append(anomaly_record)
                anomaly_counter += 1

        return all_anomalies

    def _generate_severity_distribution(
        self, anomalies: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Generate severity distribution based on z-scores.

        Detection fires at z > 3.0, so the previous high cut (z > 3.0) labelled
        every detected anomaly "high" and the "（高 N）" badge was meaningless.
        Re-stratified against the observed z distribution (min 3.0 / median 3.34
        / max 5.24): high z > 4.5, medium 3.5 < z <= 4.5, low z <= 3.5 (#666).

        Args:
            anomalies: List of anomaly records.

        Returns:
            Dict with high/medium/low severity counts.
        """
        high = sum(1 for a in anomalies if abs(a["z_score"]) > 4.5)
        medium = sum(1 for a in anomalies if 3.5 < abs(a["z_score"]) <= 4.5)
        low = sum(1 for a in anomalies if abs(a["z_score"]) <= 3.5)

        return {"high": high, "medium": medium, "low": low}

    def _generate_temporal_clusters(
        self, anomalies: list[dict[str, Any]], cluster_window: int = 300
    ) -> list[dict[str, int]]:
        """Generate temporal clusters (5-minute windows by default).

        Args:
            anomalies: List of anomaly records.
            cluster_window: Cluster window size in seconds (default: 300 = 5min).

        Returns:
            List of cluster dicts with start, end, count.
        """
        if not anomalies:
            return []

        # Sort by timestamp
        sorted_anomalies = sorted(anomalies, key=lambda a: a["timestamp"])

        # Group into clusters
        clusters = []
        current_start = (
            sorted_anomalies[0]["timestamp"] // cluster_window
        ) * cluster_window
        current_count = 0

        for anomaly in sorted_anomalies:
            anomaly_window = (anomaly["timestamp"] // cluster_window) * cluster_window
            if anomaly_window == current_start:
                current_count += 1
            else:
                if current_count > 0:
                    clusters.append(
                        {
                            "start": current_start,
                            "end": current_start + cluster_window,
                            "count": current_count,
                        }
                    )
                current_start = anomaly_window
                current_count = 1

        # Add last cluster
        if current_count > 0:
            clusters.append(
                {
                    "start": current_start,
                    "end": current_start + cluster_window,
                    "count": current_count,
                }
            )

        return clusters

    def _apply_anomaly_filters(
        self, anomalies: list[dict[str, Any]], filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Apply filters to anomaly list.

        Args:
            anomalies: List of anomaly records.
            filters: Filter criteria dict with optional keys:
                - "anomaly_ids": [int, ...] - Specific anomaly IDs
                - "time_range": (start, end) - Timestamp range
                - "metrics": [str, ...] - Metric names
                - "min_z_score": float - Minimum z-score
                - "causes": [str, ...] - Probable causes
                - "limit": int - Max results

        Returns:
            Filtered anomaly list.
        """
        filtered = anomalies.copy()

        # Filter by anomaly IDs
        if "anomaly_ids" in filters:
            ids = set(filters["anomaly_ids"])
            filtered = [a for a in filtered if a["anomaly_id"] in ids]

        # Filter by time range
        if "time_range" in filters:
            start, end = filters["time_range"]
            filtered = [a for a in filtered if start <= a["timestamp"] <= end]

        # Filter by metrics
        if "metrics" in filters:
            metrics = set(filters["metrics"])
            filtered = [a for a in filtered if a["metric"] in metrics]

        # Filter by min z-score
        if "min_z_score" in filters:
            min_z = filters["min_z_score"]
            filtered = [a for a in filtered if abs(a["z_score"]) >= min_z]

        # Filter by causes
        if "causes" in filters:
            causes = set(filters["causes"])
            filtered = [a for a in filtered if a["probable_cause"] in causes]

        # Limit results (after sorting by z-score descending)
        if "limit" in filters:
            # Sort by z-score (descending) for importance
            filtered.sort(key=lambda a: abs(a["z_score"]), reverse=True)
            filtered = filtered[: filters["limit"]]

        return filtered

    def detect_form_anomalies_summary(
        self,
        activity_id: int,
        metrics: list[str] | None = None,
        z_threshold: float = DEFAULT_Z_THRESHOLD,
    ) -> dict[str, Any]:
        """Detect form metric anomalies and return summary only (lightweight).

        This method provides a high-level overview of detected anomalies without
        detailed context information, significantly reducing token consumption
        (~90% reduction compared to full detail API).

        Args:
            activity_id: Activity ID.
            metrics: List of metric names to analyze
                    (default: ["directGroundContactTime",
                               "directVerticalOscillation",
                               "directVerticalRatio"]).
            z_threshold: Z-score threshold for anomaly detection (default: 3.0).

        Returns:
            Dictionary with anomaly summary:
            {
                "activity_id": int,
                "anomalies_detected": int,
                "summary": {
                    "gct_anomalies": int,
                    "vo_anomalies": int,
                    "vr_anomalies": int,
                    "elevation_related": int,
                    "pace_related": int,
                    "fatigue_related": int,
                    "isolated_related": int,  # spikes with no identifiable cause
                    "severity_distribution": {
                        "high": int,    # z > 4.5
                        "medium": int,  # 3.5 < z <= 4.5
                        "low": int      # z <= 3.5
                    },
                    "temporal_clusters": [
                        {"start": int, "end": int, "count": int},
                        ...
                    ]
                },
                "top_anomalies": [  # Top 5 most severe
                    {
                        "timestamp": int,
                        "metric": str,
                        "z_score": float,
                        "probable_cause": str
                    },
                    ...
                ],
                "recommendations": [str, ...]
            }
        """
        # Extract time series
        metric_map, form_metrics, context_metrics = self._extract_time_series(
            activity_id, metrics
        )

        # Detect all anomalies
        all_anomalies = self._detect_all_anomalies(
            form_metrics,
            context_metrics["elevation"],
            context_metrics["pace"],
            context_metrics["hr"],
            z_threshold,
            context_window=30,  # Not used in summary, but needed for full detection
        )

        # Generate summary statistics
        summary = {
            "gct_anomalies": sum(
                1 for a in all_anomalies if a["metric"] == "directGroundContactTime"
            ),
            "vo_anomalies": sum(
                1 for a in all_anomalies if a["metric"] == "directVerticalOscillation"
            ),
            "vr_anomalies": sum(
                1 for a in all_anomalies if a["metric"] == "directVerticalRatio"
            ),
            "elevation_related": sum(
                1 for a in all_anomalies if a["probable_cause"] == "elevation_change"
            ),
            "pace_related": sum(
                1 for a in all_anomalies if a["probable_cause"] == "pace_change"
            ),
            "fatigue_related": sum(
                1 for a in all_anomalies if a["probable_cause"] == "fatigue"
            ),
            "isolated_related": sum(
                1 for a in all_anomalies if a["probable_cause"] == "isolated"
            ),
            "severity_distribution": self._generate_severity_distribution(
                all_anomalies
            ),
            "temporal_clusters": self._generate_temporal_clusters(all_anomalies),
        }

        # Get top 5 anomalies (by z-score)
        top_anomalies = sorted(
            all_anomalies, key=lambda a: abs(a["z_score"]), reverse=True
        )[:5]
        top_anomalies_summary = [
            {
                "timestamp": a["timestamp"],
                "metric": a["metric"],
                "z_score": round(a["z_score"], 2),
                "probable_cause": a["probable_cause"],
            }
            for a in top_anomalies
        ]

        # Generate recommendations from cause-classified anomalies (#666).
        recommendations = self._generate_recommendations(all_anomalies)

        return {
            "activity_id": activity_id,
            "anomalies_detected": len(all_anomalies),
            "summary": summary,
            "top_anomalies": top_anomalies_summary,
            "recommendations": recommendations,
        }

    def get_form_anomaly_details(
        self,
        activity_id: int,
        metrics: list[str] | None = None,
        z_threshold: float = DEFAULT_Z_THRESHOLD,
        context_window: int = 30,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get detailed anomaly information with optional filtering.

        This method returns full anomaly details including context and cause analysis.
        Use filters to reduce token consumption by retrieving only relevant anomalies.

        Args:
            activity_id: Activity ID.
            metrics: List of metric names to analyze
                    (default: ["directGroundContactTime",
                               "directVerticalOscillation",
                               "directVerticalRatio"]).
            z_threshold: Z-score threshold for anomaly detection (default: 3.0).
            context_window: Context window size in seconds (default: 30).
            filters: Optional filters dict with keys:
                - "anomaly_ids": [int, ...] - Specific anomaly IDs
                - "time_range": (start, end) - Timestamp range in seconds
                - "metrics": [str, ...] - Metric names to include
                - "min_z_score": float - Minimum z-score threshold
                - "causes": [str, ...] - Probable causes ("elevation_change",
                                          "pace_change", "fatigue")
                - "limit": int - Max results (default: 50)

        Returns:
            Dictionary with detailed anomaly information:
            {
                "activity_id": int,
                "total_anomalies": int,
                "returned_anomalies": int,
                "anomalies": [
                    {
                        "anomaly_id": int,
                        "timestamp": int,
                        "metric": str,
                        "value": float,
                        "baseline": float,
                        "z_score": float,
                        "probable_cause": str,
                        "cause_details": dict,
                        "context": dict
                    },
                    ...
                ]
            }

        Examples:
            # Get elevation-related anomalies only
            details = get_form_anomaly_details(
                activity_id=12345,
                filters={"causes": ["elevation_change"], "limit": 10}
            )

            # Get anomalies in specific time range (15-20 minutes)
            details = get_form_anomaly_details(
                activity_id=12345,
                filters={"time_range": (900, 1200)}
            )

            # Get severe anomalies only (z > 3.0)
            details = get_form_anomaly_details(
                activity_id=12345,
                filters={"min_z_score": 3.0}
            )
        """
        # Extract time series
        metric_map, form_metrics, context_metrics = self._extract_time_series(
            activity_id, metrics
        )

        # Detect all anomalies
        all_anomalies = self._detect_all_anomalies(
            form_metrics,
            context_metrics["elevation"],
            context_metrics["pace"],
            context_metrics["hr"],
            z_threshold,
            context_window,
        )

        # Apply filters if provided
        if filters is None:
            filters = {"limit": 50}  # Default limit
        elif "limit" not in filters:
            filters["limit"] = 50

        filtered_anomalies = self._apply_anomaly_filters(all_anomalies, filters)

        return {
            "activity_id": activity_id,
            "total_anomalies": len(all_anomalies),
            "returned_anomalies": len(filtered_anomalies),
            "anomalies": filtered_anomalies,
        }
