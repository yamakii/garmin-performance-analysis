"""
TimeSeriesMetricsInserter - Insert time series metrics from activity_details.json to DuckDB

Inserts second-by-second time series data (26 metrics × 1000-2000 seconds) into
time_series_metrics table for efficient querying and token-optimized access.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_time_series_metrics(
    activity_details_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert time series metrics from activity_details.json to DuckDB.

    Args:
        activity_details_file: Path to raw/activity/{activity_id}/activity_details.json
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)

    Returns:
        True if successful, False otherwise

    Process:
        1. Load activity_details.json
        2. Parse metricDescriptors for name->index mapping
        3. Extract activityDetailMetrics array
        4. Convert each data point:
           - Extract timestamp_s from sumDuration
           - Apply unit conversions (factors)
           - Map metric names to normalized column names
        5. Batch insert (~1000-2000 rows/activity)
        6. Handle duplicates (DELETE before INSERT)
    """
    try:
        # Load activity_details.json
        activity_details_path = Path(activity_details_file)
        if not activity_details_path.exists():
            logger.error(f"Activity details file not found: {activity_details_file}")
            return False

        with open(activity_details_path, encoding="utf-8") as f:
            activity_details = json.load(f)

        # Validate required fields
        metric_descriptors = activity_details.get("metricDescriptors")
        activity_detail_metrics = activity_details.get("activityDetailMetrics")

        if not metric_descriptors or not isinstance(metric_descriptors, list):
            logger.error(
                "Missing or invalid metricDescriptors in activity_details.json"
            )
            return False

        if not activity_detail_metrics or not isinstance(activity_detail_metrics, list):
            logger.error(
                "Missing or invalid activityDetailMetrics in activity_details.json"
            )
            return False

        # Build metric descriptor mapping: key -> (index, factor)
        metric_map = {}
        for descriptor in metric_descriptors:
            key = descriptor.get("key")
            index = descriptor.get("metricsIndex")
            factor = descriptor.get("unit", {}).get("factor", 1.0)
            if key is not None and index is not None:
                metric_map[key] = {"index": index, "factor": factor}

        # Define column order and API key mapping
        column_spec = [
            ("sumMovingDuration", "sum_moving_duration"),
            ("sumDuration", "sum_duration"),
            ("sumElapsedDuration", "sum_elapsed_duration"),
            ("sumDistance", "sum_distance"),
            ("sumAccumulatedPower", "sum_accumulated_power"),
            ("directHeartRate", "heart_rate"),
            ("directSpeed", "speed"),
            ("directGradeAdjustedSpeed", "grade_adjusted_speed"),
            ("directRunCadence", "cadence"),
            ("directPower", "power"),
            ("directGroundContactTime", "ground_contact_time"),
            ("directVerticalOscillation", "vertical_oscillation"),
            ("directVerticalRatio", "vertical_ratio"),
            ("directStrideLength", "stride_length"),
            ("directVerticalSpeed", "vertical_speed"),
            ("directElevation", "elevation"),
            ("directAirTemperature", "air_temperature"),
            ("directLatitude", "latitude"),
            ("directLongitude", "longitude"),
            ("directAvailableStamina", "available_stamina"),
            ("directPotentialStamina", "potential_stamina"),
            ("directBodyBattery", "body_battery"),
            ("directPerformanceCondition", "performance_condition"),
            ("directFractionalCadence", "fractional_cadence"),
            ("directDoubleCadence", "double_cadence"),
        ]

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure time_series_metrics table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS time_series_metrics (
                activity_id BIGINT NOT NULL,
                timestamp_s INTEGER NOT NULL,
                sum_moving_duration DOUBLE,
                sum_duration DOUBLE,
                sum_elapsed_duration DOUBLE,
                sum_distance DOUBLE,
                sum_accumulated_power DOUBLE,
                heart_rate DOUBLE,
                speed DOUBLE,
                grade_adjusted_speed DOUBLE,
                cadence DOUBLE,
                power DOUBLE,
                ground_contact_time DOUBLE,
                vertical_oscillation DOUBLE,
                vertical_ratio DOUBLE,
                stride_length DOUBLE,
                vertical_speed DOUBLE,
                elevation DOUBLE,
                air_temperature DOUBLE,
                latitude DOUBLE,
                longitude DOUBLE,
                available_stamina DOUBLE,
                potential_stamina DOUBLE,
                body_battery DOUBLE,
                performance_condition DOUBLE,
                fractional_cadence DOUBLE,
                double_cadence DOUBLE,
                PRIMARY KEY (activity_id, timestamp_s)
            )
            """
        )

        # Create indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_time_series_activity "
            "ON time_series_metrics(activity_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_time_series_timestamp "
            "ON time_series_metrics(activity_id, timestamp_s)"
        )

        # Delete existing data for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM time_series_metrics WHERE activity_id = ?", [activity_id]
        )

        # Find sumDuration index
        sum_duration_info = metric_map.get("sumDuration")
        if not sum_duration_info:
            logger.error("sumDuration metric not found in metricDescriptors")
            conn.close()
            return False

        sum_duration_index = sum_duration_info["index"]
        sum_duration_factor = sum_duration_info["factor"]

        # Pre-compute metric extraction info (index, factor) for each column
        metric_extract_info: list[tuple[int, float] | None] = []
        for api_key, _ in column_spec:
            metric_info = metric_map.get(api_key)
            if metric_info:
                metric_extract_info.append(
                    (metric_info["index"], metric_info["factor"])
                )
            else:
                metric_extract_info.append(None)

        # Prepare batch insert data (direct tuple building for performance)
        value_tuples = []
        for data_point in activity_detail_metrics:
            metrics = data_point.get("metrics")
            if not metrics or not isinstance(metrics, list):
                continue

            # Calculate timestamp_s from sumDuration
            sum_duration_value = metrics[sum_duration_index]
            if sum_duration_value is None:
                continue

            timestamp_s = int(sum_duration_value / sum_duration_factor)

            # Build row tuple directly (avoid dict overhead)
            row_values: list[int | float | None] = [activity_id, timestamp_s]

            for extract_info in metric_extract_info:
                if extract_info is None:
                    row_values.append(None)
                    continue

                index, factor = extract_info

                # Get raw value
                if index >= len(metrics):
                    row_values.append(None)
                    continue

                raw_value = metrics[index]
                if raw_value is None:
                    row_values.append(None)
                    continue

                # Apply unit conversion
                if factor == 1.0:
                    converted_value = float(raw_value)
                elif factor > 1.0:
                    # Division (e.g., elevation: 50000 / 100.0 = 500.0)
                    converted_value = float(raw_value) / factor
                else:
                    # Multiplication (e.g., speed: 30 × 0.1 = 3.0)
                    converted_value = float(raw_value) * factor

                row_values.append(converted_value)

            value_tuples.append(tuple(row_values))

        # Batch insert
        if value_tuples:
            # Build INSERT statement
            columns = ["activity_id", "timestamp_s"] + [
                col_name for _, col_name in column_spec
            ]
            placeholders = ", ".join(["?" for _ in columns])
            column_names = ", ".join(columns)
            insert_sql = f"INSERT INTO time_series_metrics ({column_names}) VALUES ({placeholders})"

            # Execute batch insert
            conn.executemany(insert_sql, value_tuples)

        conn.close()

        logger.info(
            f"Successfully inserted {len(value_tuples)} time series metrics for activity {activity_id}"
        )
        return True

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in activity_details.json: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inserting time series metrics: {e}")
        return False
