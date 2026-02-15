"""Time series detail extraction for specific splits.

This module provides functionality to:
- Extract second-by-second metrics for specific 1km splits
- Calculate statistics (mean, std, min, max)
- Detect anomalies within splits
- Convert split numbers to time ranges
"""

import statistics
from pathlib import Path
from typing import Any

from garmin_mcp.rag.loaders.activity_details_loader import ActivityDetailsLoader


class TimeSeriesDetailExtractor:
    """Extractor for detailed time series data within splits.

    Provides methods to extract second-by-second metrics for specific
    1km splits, calculate statistics, and detect anomalies.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize TimeSeriesDetailExtractor.

        Args:
            base_path: Base directory path for data files.
                      Defaults to GARMIN_DATA_DIR from environment if not provided.
        """
        if base_path is None:
            from garmin_mcp.utils.paths import get_data_base_dir

            base_path = get_data_base_dir()
        self.base_path = base_path
        self.loader = ActivityDetailsLoader(base_path=self.base_path)

    def _split_to_time_range(
        self, split_number: int, splits_data: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Convert split number (1-based) to time range (start_time_s, end_time_s).

        Args:
            split_number: Split number (1-based indexing).
            splits_data: List of split data dictionaries with start_time_s and end_time_s.

        Returns:
            Tuple of (start_time_s, end_time_s).

        Raises:
            ValueError: If split_number is invalid (0, negative, or exceeds total splits).
        """
        if split_number < 1:
            raise ValueError(f"Split number must be >= 1, got {split_number}")

        if split_number > len(splits_data):
            raise ValueError(
                f"Split number {split_number} exceeds total splits {len(splits_data)}"
            )

        # Convert 1-based split number to 0-based index
        split_index = split_number - 1
        split_data = splits_data[split_index]

        return split_data["start_time_s"], split_data["end_time_s"]

    def _get_split_time_range(
        self, activity_id: int, split_number: int
    ) -> tuple[int, int]:
        """Get time range for a split from DuckDB.

        Args:
            activity_id: Activity ID.
            split_number: Split number (1-based).

        Returns:
            Tuple of (start_time_s, end_time_s).

        Raises:
            ValueError: If split not found or invalid.
        """
        import duckdb

        from garmin_mcp.database.db_reader import GarminDBReader

        db_reader = GarminDBReader()

        try:
            conn = duckdb.connect(str(db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT start_time_s, end_time_s
                FROM splits
                WHERE activity_id = ? AND split_index = ?
                """,
                [activity_id, split_number],  # split_index is 1-based in DuckDB
            ).fetchone()

            conn.close()

            if not result:
                raise ValueError(
                    f"Split {split_number} not found for activity {activity_id}"
                )

            return result[0], result[1]

        except Exception as e:
            raise ValueError(f"Error querying DuckDB: {e}") from e

    def extract_metrics(
        self,
        activity_id: int,
        start_time: int,
        end_time: int,
        metrics: list[str] | None = None,
        use_duckdb: bool | None = None,
        statistics_only: bool = False,
    ) -> dict[str, Any]:
        """Extract second-by-second metrics for specified time range.

        Args:
            activity_id: Activity ID.
            start_time: Start time in seconds.
            end_time: End time in seconds.
            metrics: List of metric names to extract. If None, uses default set.
            use_duckdb: Use DuckDB for efficient extraction.
                       None (default): Auto-detect - use DuckDB if data exists, else JSON.
                       True: Force DuckDB (raises error if data not in DuckDB).
                       False: Force JSON-based extraction.
            statistics_only: If True, only return statistics (not full time series).
                            Provides maximum token reduction (~99.8%).

        Returns:
            Dictionary with extracted metrics:
            {
                "activity_id": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "metrics": [str],
                "statistics": {metric: {mean, std, min, max}},
                "time_series": [{"timestamp_s": int, "metric1": float, ...}]  # Only if statistics_only=False
            }
        """
        # Default metrics if not specified
        if metrics is None:
            metrics = [
                "heart_rate",
                "speed",
                "cadence",
                "power",
                "vertical_oscillation",
                "ground_contact_time",
                "vertical_ratio",
            ]

        # Auto-detect DuckDB availability if not specified
        if use_duckdb is None:
            use_duckdb = self._is_in_duckdb(activity_id)

        if use_duckdb:
            # Use DuckDB for efficient extraction
            from garmin_mcp.database.db_reader import GarminDBReader

            db_reader = GarminDBReader()

            # Get statistics (always needed for statistics_only)
            stats_result = db_reader.get_time_series_statistics(
                activity_id=activity_id,
                start_time_s=start_time,
                end_time_s=end_time,
                metrics=metrics,
            )

            if "error" in stats_result:
                return {
                    "activity_id": activity_id,
                    "error": stats_result["error"],
                }

            # Convert 'avg' to 'mean' for compatibility
            stats = {}
            for metric, stat_dict in stats_result["statistics"].items():
                stats[metric] = {
                    "mean": stat_dict["avg"],
                    "std": stat_dict["std"],
                    "min": stat_dict["min"],
                    "max": stat_dict["max"],
                }

            response = {
                "activity_id": activity_id,
                "time_range": {"start_time_s": start_time, "end_time_s": end_time},
                "metrics": metrics,
                "statistics": stats,
            }

            # Only include time series if not statistics_only
            if not statistics_only:
                raw_result = db_reader.get_time_series_raw(
                    activity_id=activity_id,
                    start_time_s=start_time,
                    end_time_s=end_time,
                    metrics=metrics,
                )
                response["time_series"] = raw_result.get("time_series", [])

            return response

        # Legacy JSON-based extraction
        try:
            # Load activity details
            activity_details = self.loader.load_activity_details(activity_id)

            # Parse metric descriptors
            metric_descriptors = activity_details["metricDescriptors"]
            metric_map = self.loader.parse_metric_descriptors(metric_descriptors)

            # Get time series data
            metrics_data = activity_details["activityDetailMetrics"]

            # Map metric names to metric keys in activity_details
            metric_key_map = {
                "heart_rate": "directHeartRate",
                "speed": "directSpeed",
                "cadence": "directRunCadence",
                "power": "directPower",
                "vertical_oscillation": "directVerticalOscillation",
                "ground_contact_time": "directGroundContactTime",
                "vertical_ratio": "directVerticalRatio",
            }

            # Extract time series for requested metrics
            time_series: list[dict[str, Any]] = []
            for timestamp_idx in range(start_time, end_time):
                if timestamp_idx >= len(metrics_data):
                    break

                data_point: dict[str, Any] = {"timestamp_s": timestamp_idx}

                for metric_name in metrics:
                    metric_key = metric_key_map.get(metric_name)
                    if metric_key and metric_key in metric_map:
                        metric_info = metric_map[metric_key]
                        metric_index = metric_info["index"]

                        # Get raw value
                        measurement = metrics_data[timestamp_idx]
                        metric_values = measurement["metrics"]

                        if metric_index < len(metric_values):
                            raw_value = metric_values[metric_index]
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
                    else:
                        data_point[metric_name] = None

                time_series.append(data_point)

            # Calculate statistics
            stats = self.calculate_statistics(
                time_series,
                metrics,
                use_duckdb=False,
            )

            response = {
                "activity_id": activity_id,
                "time_range": {"start_time_s": start_time, "end_time_s": end_time},
                "metrics": metrics,
                "statistics": stats,
            }

            # Only include time series if not statistics_only
            if not statistics_only:
                response["time_series"] = time_series

            return response

        except FileNotFoundError as e:
            return {
                "activity_id": activity_id,
                "error": f"Activity details not found: {e}",
            }
        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error extracting metrics: {e}",
            }

    def _is_in_duckdb(self, activity_id: int) -> bool:
        """Check if activity data exists in DuckDB.

        Args:
            activity_id: Activity ID to check.

        Returns:
            True if activity data exists in time_series_metrics table.
        """
        try:
            import duckdb

            from garmin_mcp.database.db_reader import GarminDBReader

            db_reader = GarminDBReader()
            conn = duckdb.connect(str(db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT COUNT(*)
                FROM time_series_metrics
                WHERE activity_id = ?
                LIMIT 1
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            return result[0] > 0 if result else False
        except Exception:
            return False

    def calculate_statistics(
        self,
        time_series_data: list[dict[str, Any]] | None,
        metrics: list[str],
        activity_id: int | None = None,
        start_time_s: int | None = None,
        end_time_s: int | None = None,
        use_duckdb: bool | None = None,
    ) -> dict[str, dict[str, float]]:
        """Calculate statistics for each metric in time series data.

        Args:
            time_series_data: List of data points with timestamps and metric values.
                             Can be None if using DuckDB mode.
            metrics: List of metric names to calculate statistics for.
            activity_id: Activity ID (required for DuckDB mode).
            start_time_s: Start time in seconds (required for DuckDB mode).
            end_time_s: End time in seconds (required for DuckDB mode).
            use_duckdb: Use DuckDB for efficient statistics calculation.
                       None (default): Auto-detect based on available parameters.
                       True: Force DuckDB (requires activity_id, start_time_s, end_time_s).
                       False: Force Python-based calculation (requires time_series_data).

        Returns:
            Dictionary mapping metric names to their statistics:
            {
                "metric_name": {
                    "mean": float,
                    "std": float,
                    "min": float,
                    "max": float
                }
            }
        """
        # Auto-detect mode
        if use_duckdb is None:
            # Prefer DuckDB if we have the required parameters
            if (
                activity_id is not None
                and start_time_s is not None
                and end_time_s is not None
            ):
                use_duckdb = self._is_in_duckdb(activity_id)
            else:
                use_duckdb = False

        if use_duckdb:
            # Use DuckDB for efficient SQL-based statistics
            if activity_id is None or start_time_s is None or end_time_s is None:
                raise ValueError(
                    "activity_id, start_time_s, end_time_s required for DuckDB mode"
                )

            from garmin_mcp.database.db_reader import GarminDBReader

            db_reader = GarminDBReader()
            result = db_reader.get_time_series_statistics(
                activity_id=activity_id,
                start_time_s=start_time_s,
                end_time_s=end_time_s,
                metrics=metrics,
            )

            if "error" in result:
                return {}

            # Convert 'avg' to 'mean' for compatibility
            stats_duckdb: dict[str, dict[str, float]] = {}
            for metric, stat_dict in result["statistics"].items():
                stats_duckdb[metric] = {
                    "mean": stat_dict["avg"],
                    "std": stat_dict["std"],
                    "min": stat_dict["min"],
                    "max": stat_dict["max"],
                }
            return stats_duckdb

        # Legacy Python-based statistics
        if time_series_data is None:
            raise ValueError("time_series_data required for non-DuckDB mode")

        stats: dict[str, dict[str, float]] = {}

        for metric in metrics:
            # Extract non-None values for this metric
            values = [
                point[metric]
                for point in time_series_data
                if point.get(metric) is not None
            ]

            if values:
                stats[metric] = {
                    "mean": float(statistics.mean(values)),
                    "std": float(statistics.stdev(values) if len(values) > 1 else 0.0),
                    "min": float(min(values)),
                    "max": float(max(values)),
                }
            else:
                stats[metric] = {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}

        return stats

    def detect_anomalies(
        self,
        time_series_data: list[dict[str, Any]],
        metrics: list[str],
        z_threshold: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Detect anomalies in time series data using z-score.

        Args:
            time_series_data: List of data points with timestamps and metric values.
            metrics: List of metric names to check for anomalies.
            z_threshold: Z-score threshold for anomaly detection (default: 2.0).

        Returns:
            List of anomalies:
            [
                {
                    "timestamp_s": int,
                    "metric": str,
                    "value": float,
                    "z_score": float
                }
            ]
        """
        anomalies = []

        for metric in metrics:
            # Extract non-None values
            values = [
                point[metric]
                for point in time_series_data
                if point.get(metric) is not None
            ]

            if len(values) <= 1:
                continue

            # Calculate mean and std
            mean = statistics.mean(values)
            std = statistics.stdev(values)

            if std == 0:
                continue

            # Check each data point for anomalies
            for point in time_series_data:
                value = point.get(metric)
                if value is None:
                    continue

                z_score = (value - mean) / std

                if abs(z_score) > z_threshold:
                    anomalies.append(
                        {
                            "timestamp_s": point["timestamp_s"],
                            "metric": metric,
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
        detect_anomalies: bool = False,
        z_threshold: float = 2.0,
        use_duckdb: bool | None = None,
        statistics_only: bool = False,
    ) -> dict[str, Any]:
        """Get detailed time series data for a specific split.

        Args:
            activity_id: Activity ID.
            split_number: Split number (1-based indexing).
            metrics: List of metric names to extract. If None, uses default set.
            detect_anomalies: Whether to detect anomalies in the data.
            z_threshold: Z-score threshold for anomaly detection (default: 2.0).
            use_duckdb: Use DuckDB for efficient extraction.
                       None (default): Auto-detect.
                       Provides ~90% token reduction vs JSON-based approach.
            statistics_only: If True, only return statistics (not full time series).
                            Provides maximum token reduction (~98%).

        Returns:
            Dictionary with split time series detail:
            {
                "activity_id": int,
                "split_number": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "metrics": [str],
                "statistics": {metric: {mean, std, min, max}},
                "time_series": [{\"timestamp_s\": int, "metric1": float, ...}],  # Only if statistics_only=False
                "anomalies": [...] (if detect_anomalies=True)
            }
        """
        try:
            # Get time range from DuckDB
            start_time, end_time = self._get_split_time_range(activity_id, split_number)

            # Default metrics
            if metrics is None:
                metrics = [
                    "heart_rate",
                    "speed",
                    "cadence",
                    "power",
                    "vertical_oscillation",
                    "ground_contact_time",
                    "vertical_ratio",
                ]

            # Auto-detect DuckDB if not specified
            if use_duckdb is None:
                use_duckdb = self._is_in_duckdb(activity_id)

            if use_duckdb:
                # DuckDB-optimized path: 90-98% token reduction
                from garmin_mcp.database.db_reader import GarminDBReader

                db_reader = GarminDBReader()

                # Get statistics (compact)
                stats_result = db_reader.get_time_series_statistics(
                    activity_id=activity_id,
                    start_time_s=start_time,
                    end_time_s=end_time,
                    metrics=metrics,
                )

                if "error" in stats_result:
                    return {
                        "activity_id": activity_id,
                        "split_number": split_number,
                        "error": stats_result["error"],
                    }

                # Convert 'avg' to 'mean' for compatibility
                stats = {}
                for metric, stat_dict in stats_result["statistics"].items():
                    stats[metric] = {
                        "mean": stat_dict["avg"],
                        "std": stat_dict["std"],
                        "min": stat_dict["min"],
                        "max": stat_dict["max"],
                    }

                response = {
                    "activity_id": activity_id,
                    "split_number": split_number,
                    "time_range": {"start_time_s": start_time, "end_time_s": end_time},
                    "metrics": metrics,
                    "statistics": stats,
                }

                # Only include time series if requested
                if not statistics_only:
                    raw_result = db_reader.get_time_series_raw(
                        activity_id=activity_id,
                        start_time_s=start_time,
                        end_time_s=end_time,
                        metrics=metrics,
                    )
                    response["time_series"] = raw_result.get("time_series", [])

                # Detect anomalies if requested (using DuckDB)
                if detect_anomalies:
                    anomaly_result = db_reader.detect_anomalies_sql(
                        activity_id=activity_id,
                        metrics=metrics,
                        z_threshold=z_threshold,
                    )

                    # Filter anomalies to this split's time range
                    split_anomalies = [
                        a
                        for a in anomaly_result.get("anomalies", [])
                        if start_time <= a["timestamp_s"] < end_time
                    ]
                    response["anomalies"] = split_anomalies

                return response

            # Legacy JSON-based path
            # Extract metrics
            result = self.extract_metrics(
                activity_id, start_time, end_time, metrics, use_duckdb=False
            )

            if "error" in result:
                return result

            # Calculate statistics
            stats = self.calculate_statistics(
                result["time_series"],
                result["metrics"],
                use_duckdb=False,
            )

            # Build response
            response = {
                "activity_id": activity_id,
                "split_number": split_number,
                "time_range": result["time_range"],
                "metrics": result["metrics"],
                "statistics": stats,
            }

            # Only include time series if requested
            if not statistics_only:
                response["time_series"] = result["time_series"]

            # Detect anomalies if requested
            if detect_anomalies:
                anomalies = self.detect_anomalies(
                    result["time_series"], result["metrics"], z_threshold
                )
                response["anomalies"] = anomalies

            return response

        except ValueError as e:
            return {
                "activity_id": activity_id,
                "split_number": split_number,
                "error": str(e),
            }
        except FileNotFoundError:
            return {
                "activity_id": activity_id,
                "split_number": split_number,
                "error": f"Activity details not found for activity {activity_id}",
            }
        except Exception as e:
            return {
                "activity_id": activity_id,
                "split_number": split_number,
                "error": f"Error extracting split time series: {e}",
            }
