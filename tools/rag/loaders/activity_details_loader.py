"""ActivityDetailsLoader - Loads and parses Garmin activity_details.json files.

This module provides functionality to load activity_details.json files from the
data/raw/activity/{activity_id}/ directory and parse the metric descriptors and
time series data.
"""

import json
from pathlib import Path
from typing import Any


class ActivityDetailsLoader:
    """Loads and parses Garmin activity_details.json files.

    The ActivityDetailsLoader provides methods to:
    - Load activity_details.json from disk
    - Parse metric descriptors into a name -> index mapping
    - Extract time series data for specific metrics
    - Apply unit conversions based on metric descriptors

    Attributes:
        base_path: Base directory path for data files (defaults to current directory)
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize ActivityDetailsLoader.

        Args:
            base_path: Base directory path for data files.
                      Defaults to current directory if not provided.
        """
        self.base_path = base_path or Path(".")

    def load_activity_details(self, activity_id: int) -> dict[str, Any]:
        """Load activity_details.json from data/raw/activity/{activity_id}/.

        Args:
            activity_id: The Garmin activity ID.

        Returns:
            Dictionary containing the activity details JSON data.

        Raises:
            FileNotFoundError: If the activity_details.json file doesn't exist.
            json.JSONDecodeError: If the JSON file is malformed.
        """
        file_path = (
            self.base_path
            / "data"
            / "raw"
            / "activity"
            / str(activity_id)
            / "activity_details.json"
        )

        if not file_path.exists():
            raise FileNotFoundError(
                f"activity_details.json not found for activity {activity_id} at {file_path}"
            )

        with open(file_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            return data

    def parse_metric_descriptors(
        self, metric_descriptors: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Parse metricDescriptors array and create name -> metadata mapping.

        Args:
            metric_descriptors: List of metric descriptor dictionaries from
                               activity_details.json.

        Returns:
            Dictionary mapping metric key names to their metadata:
            {
                "metricName": {
                    "index": int,        # Index in the metrics array
                    "unit": str,         # Unit key (e.g., "second", "bpm")
                    "unit_id": int,      # Unit ID
                    "factor": float      # Conversion factor
                }
            }

        Example:
            >>> descriptors = [
            ...     {
            ...         "metricsIndex": 0,
            ...         "key": "sumElapsedDuration",
            ...         "unit": {"id": 40, "key": "second", "factor": 1000.0}
            ...     }
            ... ]
            >>> loader.parse_metric_descriptors(descriptors)
            {
                "sumElapsedDuration": {
                    "index": 0,
                    "unit": "second",
                    "unit_id": 40,
                    "factor": 1000.0
                }
            }
        """
        metric_map = {}

        for descriptor in metric_descriptors:
            key = descriptor["key"]
            unit_info = descriptor["unit"]

            metric_map[key] = {
                "index": descriptor["metricsIndex"],
                "unit": unit_info["key"],
                "unit_id": unit_info["id"],
                "factor": unit_info["factor"],
            }

        return metric_map

    def extract_time_series(
        self,
        metrics: list[dict[str, list]],
        metric_index: int,
        start_index: int = 0,
        end_index: int | None = None,
    ) -> list[float | None]:
        """Extract time series data for a specific metric.

        Args:
            metrics: List of activityDetailMetrics from activity_details.json.
            metric_index: Index of the metric to extract (from metricDescriptors).
            start_index: Starting measurement index (inclusive, default: 0).
            end_index: Ending measurement index (exclusive, default: None for all).

        Returns:
            List of metric values for the specified time range.
            None values are preserved for missing data points.

        Example:
            >>> metrics = [
            ...     {"metrics": [1000.0, 170.0, 130.0]},
            ...     {"metrics": [2000.0, 175.0, 135.0]}
            ... ]
            >>> loader.extract_time_series(metrics, metric_index=1)
            [170.0, 175.0]
        """
        if end_index is None:
            end_index = len(metrics)

        time_series = []
        for measurement in metrics[start_index:end_index]:
            metric_values = measurement["metrics"]
            if metric_index < len(metric_values):
                time_series.append(metric_values[metric_index])
            else:
                time_series.append(None)

        return time_series

    def apply_unit_conversion(self, metric_info: dict[str, Any], value: float) -> float:
        """Apply unit conversion using factor from metricDescriptors.

        Args:
            metric_info: Metric metadata dictionary from parse_metric_descriptors().
            value: Raw metric value to convert.

        Returns:
            Converted value (value / factor).

        Example:
            >>> metric_info = {"index": 0, "unit": "second", "factor": 1000.0}
            >>> loader.apply_unit_conversion(metric_info, 5000.0)
            5.0  # 5000.0 / 1000.0 = 5.0 seconds
        """
        factor: float = metric_info["factor"]
        return value / factor
