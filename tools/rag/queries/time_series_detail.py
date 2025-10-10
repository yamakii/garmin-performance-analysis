"""Time series detail extraction for individual splits.

This module provides functionality to extract second-by-second detailed metrics
for specific 1km splits from activity_details.json data.

Key features:
- Split number to time range conversion
- Second-by-second metric extraction
- Statistics calculation (avg, std, min, max)
- Anomaly detection within splits using z-score
- Support for all 26+ metrics from activity_details.json
"""

import json
import statistics
from pathlib import Path
from typing import Any

from tools.rag.loaders.activity_details_loader import ActivityDetailsLoader


class TimeSeriesDetailExtractor:
    """Extract second-by-second time series details for specific splits.

    This class provides methods to:
    - Convert split numbers to time ranges using performance.json
    - Extract time series data for specific metrics
    - Calculate statistics on time series data
    - Detect anomalies within splits using z-score method

    Attributes:
        base_path: Base directory path for data files
        loader: ActivityDetailsLoader instance for loading activity data
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize TimeSeriesDetailExtractor.

        Args:
            base_path: Base directory path for data files.
                      Defaults to current directory if not provided.
        """
        self.base_path = base_path or Path(".")
        self.loader = ActivityDetailsLoader(base_path=self.base_path)

    def _get_split_time_range(
        self, split_number: int, performance_data: dict[str, Any]
    ) -> tuple[int, int]:
        """Get time range (start_time_s, end_time_s) for a specific split.

        Args:
            split_number: Split number (1-based index).
            performance_data: Performance data dictionary containing split_metrics.

        Returns:
            Tuple of (start_time_s, end_time_s).

        Raises:
            ValueError: If split_number is invalid (< 1 or > max_splits).
            KeyError: If split_metrics not found in performance_data.
        """
        if "split_metrics" not in performance_data:
            raise KeyError("split_metrics not found in performance_data")

        splits = performance_data["split_metrics"]

        if split_number < 1 or split_number > len(splits):
            raise ValueError(
                f"Invalid split_number: {split_number}. "
                f"Valid range: 1-{len(splits)}"
            )

        # Get split (1-based to 0-based index)
        split = splits[split_number - 1]

        return split["start_time_s"], split["end_time_s"]

    def _extract_time_series_data(
        self,
        activity_details: dict[str, Any],
        metric_names: list[str],
        start_time_s: int,
        end_time_s: int,
    ) -> list[dict[str, Any]]:
        """Extract time series data for specific metrics within time range.

        Args:
            activity_details: Activity details data from activity_details.json.
            metric_names: List of metric names to extract.
            start_time_s: Start time in seconds.
            end_time_s: End time in seconds.

        Returns:
            List of dictionaries with time series data:
            [
                {"timestamp": 0, "metric1": value1, "metric2": value2, ...},
                {"timestamp": 1, "metric1": value1, "metric2": value2, ...},
                ...
            ]
        """
        # Parse metric descriptors
        metric_map = self.loader.parse_metric_descriptors(
            activity_details["metricDescriptors"]
        )

        # Get metrics data
        metrics_data = activity_details["activityDetailMetrics"]

        # Extract time series for requested metrics
        time_series: list[dict[str, Any]] = []

        for timestamp_idx in range(start_time_s, min(end_time_s, len(metrics_data))):
            data_point: dict[str, Any] = {"timestamp": timestamp_idx}

            for metric_name in metric_names:
                if metric_name not in metric_map:
                    # Metric not available, set to None
                    data_point[metric_name] = None
                    continue

                metric_info = metric_map[metric_name]
                metric_idx = metric_info["index"]

                # Extract raw value
                measurement = metrics_data[timestamp_idx]
                raw_values = measurement["metrics"]

                if metric_idx < len(raw_values):
                    raw_value = raw_values[metric_idx]
                    if raw_value is not None:
                        # Apply unit conversion
                        converted_value = self.loader.apply_unit_conversion(
                            metric_info, raw_value
                        )
                        data_point[metric_name] = converted_value
                    else:
                        data_point[metric_name] = None
                else:
                    data_point[metric_name] = None

            time_series.append(data_point)

        return time_series

    def _calculate_statistics(
        self, time_series: list[float | None] | tuple[float | None, ...]
    ) -> dict[str, float | int]:
        """Calculate statistics on time series data.

        Args:
            time_series: List of metric values (may contain None).

        Returns:
            Dictionary with statistics:
            {
                "avg": float,
                "std": float,
                "min": float,
                "max": float,
                "count": int  # Number of non-None values
            }
        """
        # Filter out None values
        valid_values = [v for v in time_series if v is not None]

        if not valid_values:
            return {
                "avg": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "count": 0,
            }

        return {
            "avg": statistics.mean(valid_values),
            "std": statistics.stdev(valid_values) if len(valid_values) > 1 else 0.0,
            "min": min(valid_values),
            "max": max(valid_values),
            "count": len(valid_values),
        }

    def _detect_split_anomalies(
        self,
        metric_name: str,
        time_series: list[float | None] | tuple[float | None, ...],
        z_threshold: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Detect anomalies in time series using z-score method.

        Args:
            metric_name: Name of the metric being analyzed.
            time_series: List of metric values.
            z_threshold: Z-score threshold for anomaly detection (default: 2.0).

        Returns:
            List of anomaly dictionaries:
            [
                {
                    "index": int,
                    "metric": str,
                    "value": float,
                    "z_score": float
                },
                ...
            ]
        """
        # Filter out None values for statistics
        valid_values = [v for v in time_series if v is not None]

        if len(valid_values) < 2:
            # Not enough data for anomaly detection
            return []

        # Calculate mean and std
        mean_val = statistics.mean(valid_values)
        std_val = statistics.stdev(valid_values)

        if std_val == 0:
            # No variation, no anomalies
            return []

        # Detect anomalies
        anomalies = []
        for idx, value in enumerate(time_series):
            if value is None:
                continue

            z_score = abs((value - mean_val) / std_val)

            if z_score > z_threshold:
                anomalies.append(
                    {
                        "index": idx,
                        "metric": metric_name,
                        "value": value,
                        "z_score": z_score,
                    }
                )

        return anomalies

    def get_split_time_series_detail(
        self,
        activity_id: int,
        split_number: int,
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get second-by-second time series detail for a specific split.

        Args:
            activity_id: Activity ID.
            split_number: Split number (1-based).
            metrics: List of metric names to extract (None = common metrics).

        Returns:
            Dictionary with split time series detail:
            {
                "activity_id": int,
                "split_number": int,
                "start_time_s": int,
                "end_time_s": int,
                "duration_s": int,
                "time_series": [
                    {"timestamp": 0, "metric1": value1, ...},
                    ...
                ],
                "statistics": {
                    "metric1": {"avg": ..., "std": ..., "min": ..., "max": ...},
                    ...
                },
                "anomalies": [
                    {"index": ..., "metric": ..., "value": ..., "z_score": ...},
                    ...
                ]
            }
        """
        # Default metrics if not specified
        if metrics is None:
            metrics = [
                "directHeartRate",
                "directSpeed",
                "directDoubleCadence",
                "directGroundContactTime",
                "directVerticalOscillation",
            ]

        # Load performance.json
        perf_path = self.base_path / "data" / "performance" / f"{activity_id}.json"
        with open(perf_path, encoding="utf-8") as f:
            performance_data = json.load(f)

        # Get split time range
        start_time, end_time = self._get_split_time_range(
            split_number, performance_data
        )

        # Load activity_details.json
        activity_details = self.loader.load_activity_details(activity_id)

        # Extract time series data
        time_series = self._extract_time_series_data(
            activity_details, metrics, start_time, end_time
        )

        # Calculate statistics for each metric
        statistics_dict = {}
        all_anomalies = []

        for metric_name in metrics:
            # Extract metric values
            metric_values = [tp.get(metric_name) for tp in time_series]

            # Calculate statistics
            stats = self._calculate_statistics(metric_values)
            statistics_dict[metric_name] = stats

            # Detect anomalies
            anomalies = self._detect_split_anomalies(metric_name, metric_values)
            all_anomalies.extend(anomalies)

        return {
            "activity_id": activity_id,
            "split_number": split_number,
            "start_time_s": start_time,
            "end_time_s": end_time,
            "duration_s": end_time - start_time,
            "time_series": time_series,
            "statistics": statistics_dict,
            "anomalies": all_anomalies,
        }
