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

from tools.rag.loaders.activity_details_loader import ActivityDetailsLoader


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
            from tools.utils.paths import get_data_base_dir

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

    def _detect_anomalies_by_zscore(
        self,
        metric_name: str,
        time_series: list[float | None],
        rolling_means: list[float],
        rolling_stds: list[float],
        z_threshold: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Detect anomalies using z-score method with rolling statistics.

        Args:
            metric_name: Name of the metric being analyzed.
            time_series: List of metric values.
            rolling_means: List of rolling mean values.
            rolling_stds: List of rolling standard deviation values.
            z_threshold: Z-score threshold for anomaly detection (default: 2.0).

        Returns:
            List of anomaly dictionaries with timestamp, value, z-score.
        """
        anomalies = []

        for idx, value in enumerate(time_series):
            if value is None:
                continue

            mean_val = rolling_means[idx]
            std_val = rolling_stds[idx]

            if std_val == 0:
                continue

            z_score = abs((value - mean_val) / std_val)

            if z_score > z_threshold:
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
    ) -> tuple[str, dict[str, Any]]:
        """Analyze probable cause of anomaly using correlation analysis.

        Args:
            anomaly: Anomaly dictionary with timestamp and metric info.
            elevation_series: Elevation time series.
            pace_series: Pace time series (min/km).
            hr_series: Heart rate time series.

        Returns:
            Tuple of (probable_cause, cause_details).
            Probable causes: "elevation_change", "pace_change", "fatigue"
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
        elif abs(hr_drift_percent) > 10.0:
            cause_details["hr_correlation"] = min(
                0.95, 0.5 + (abs(hr_drift_percent) / 30.0)
            )
            return "fatigue", cause_details
        else:
            # Default to pace change with low correlation
            cause_details["pace_correlation"] = 0.3
            return "pace_change", cause_details

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

    def _generate_recommendations(self, summary: dict[str, int]) -> list[str]:
        """Generate improvement recommendations based on anomaly summary.

        Args:
            summary: Anomaly summary with counts by cause.

        Returns:
            List of recommendation strings.
        """
        recommendations = []

        if summary["elevation_related"] > 0:
            recommendations.append("上り坂でGCT悪化が顕著 → 上り坂練習強化を推奨")

        if summary["pace_related"] > 0:
            recommendations.append("ペース急変時にVO増加 → ペース変化を緩やかに")

        if summary["fatigue_related"] > 0:
            recommendations.append(
                "疲労によるフォーム崩れ → 持久力トレーニング強化を推奨"
            )

        return recommendations

    def detect_form_anomalies(
        self,
        activity_id: int,
        metrics: list[str] | None = None,
        z_threshold: float = 2.0,
        context_window: int = 30,
    ) -> dict[str, Any]:
        """Detect form metric anomalies and identify probable causes.

        Args:
            activity_id: Activity ID.
            metrics: List of metric names to analyze
                    (default: ["directGroundContactTime",
                               "directVerticalOscillation",
                               "directVerticalRatio"]).
            z_threshold: Z-score threshold for anomaly detection (default: 2.0).
            context_window: Context window size in seconds (default: 30).

        Returns:
            Dictionary with anomaly detection results:
            {
                "activity_id": int,
                "anomalies_detected": int,
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
                ],
                "summary": {
                    "gct_anomalies": int,
                    "vo_anomalies": int,
                    "vr_anomalies": int,
                    "elevation_related": int,
                    "pace_related": int,
                    "fatigue_related": int
                },
                "recommendations": [str, ...]
            }
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

        # Extract contextual metrics (elevation, pace, HR)
        elevation_series = []
        pace_series = []
        hr_series = []

        for measurement in metrics_data:
            values = measurement["metrics"]

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

        # Detect anomalies for each requested metric
        all_anomalies = []
        anomaly_counter = 1

        for metric_name in metrics:
            if metric_name not in metric_map:
                continue

            # Extract metric time series
            metric_info = metric_map[metric_name]
            metric_idx = metric_info["index"]

            metric_series: list[float | None] = []
            for measurement in metrics_data:
                values = measurement["metrics"]
                if metric_idx < len(values):
                    raw_val = values[metric_idx]
                    if raw_val is not None:
                        converted_val = self.loader.apply_unit_conversion(
                            metric_info, raw_val
                        )
                        metric_series.append(converted_val)
                    else:
                        metric_series.append(None)
                else:
                    metric_series.append(None)

            # Calculate rolling statistics
            rolling_means, rolling_stds = self._calculate_rolling_stats(
                metric_series, window_size=60
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

        # Generate summary
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
        }

        # Generate recommendations
        recommendations = self._generate_recommendations(summary)

        return {
            "activity_id": activity_id,
            "anomalies_detected": len(all_anomalies),
            "anomalies": all_anomalies,
            "summary": summary,
            "recommendations": recommendations,
        }
