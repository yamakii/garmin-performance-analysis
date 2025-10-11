"""
ActivitiesInserter - Insert activity metadata from performance.json to DuckDB activities table

Populates the activities table with 36 columns of metadata for each activity.
This inserter must be called FIRST before other inserters due to foreign key constraints.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_activities(
    performance_file: str,
    activity_id: int,
    date: str,
    db_path: str | None = None,
    raw_activity_file: str | None = None,
    raw_weather_file: str | None = None,
    raw_gear_file: str | None = None,
) -> bool:
    """
    Insert activity metadata into DuckDB activities table.

    Extracts 36 columns from:
    - performance.json: basic_metrics, efficiency_metrics, training_effect, power_to_weight, split_metrics
    - activity.json (optional): activityName, startTimeLocal, startTimeGMT, locationName
    - weather.json (optional): temp, relativeHumidity, windSpeed, windDirectionCompassPoint
    - gear.json (optional): gearTypeName, customMakeModel

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
        date: Activity date (YYYY-MM-DD format)
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_activity_file: Optional path to raw activity.json
        raw_weather_file: Optional path to raw weather.json
        raw_gear_file: Optional path to raw gear.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load performance.json
        performance_path = Path(performance_file)
        if not performance_path.exists():
            logger.error(f"Performance file not found: {performance_file}")
            return False

        with open(performance_path, encoding="utf-8") as f:
            performance_data = json.load(f)

        # Extract basic_metrics (required)
        basic_metrics = performance_data.get("basic_metrics", {})
        if not basic_metrics:
            logger.error(f"No basic_metrics found in {performance_file}")
            return False

        # Extract efficiency_metrics (optional)
        efficiency_metrics = performance_data.get("efficiency_metrics", {})

        # Extract training_effect (optional)
        training_effect = performance_data.get("training_effect", {})

        # Extract power_to_weight (optional)
        power_to_weight = performance_data.get("power_to_weight", {})

        # Extract elevation from split_metrics (sum of all splits)
        split_metrics = performance_data.get("split_metrics", [])
        total_elevation_gain = sum(
            split.get("elevation_gain_m", 0) for split in split_metrics
        )
        total_elevation_loss = sum(
            split.get("elevation_loss_m", 0) for split in split_metrics
        )

        # Load optional raw data files
        activity_name = None
        start_time_local = None
        start_time_gmt = None
        location_name = None

        if raw_activity_file:
            raw_activity_path = Path(raw_activity_file)
            if raw_activity_path.exists():
                with open(raw_activity_path, encoding="utf-8") as f:
                    raw_activity = json.load(f)
                    activity_name = raw_activity.get("activityName")
                    summary_dto = raw_activity.get("summaryDTO", {})
                    start_time_local_str = summary_dto.get("startTimeLocal")
                    start_time_gmt_str = summary_dto.get("startTimeGMT")
                    location_name = raw_activity.get("locationName")

                    # Parse timestamps (format: "2025-10-09T21:50:00.0")
                    if start_time_local_str:
                        try:
                            start_time_local = datetime.strptime(
                                start_time_local_str, "%Y-%m-%dT%H:%M:%S.%f"
                            )
                        except ValueError:
                            logger.warning(
                                f"Failed to parse startTimeLocal: {start_time_local_str}"
                            )
                    if start_time_gmt_str:
                        try:
                            start_time_gmt = datetime.strptime(
                                start_time_gmt_str, "%Y-%m-%dT%H:%M:%S.%f"
                            )
                        except ValueError:
                            logger.warning(
                                f"Failed to parse startTimeGMT: {start_time_gmt_str}"
                            )

        external_temp_c = None
        external_temp_f = None
        humidity = None
        wind_speed_ms = None
        wind_direction_compass = None

        if raw_weather_file:
            raw_weather_path = Path(raw_weather_file)
            if raw_weather_path.exists():
                with open(raw_weather_path, encoding="utf-8") as f:
                    raw_weather = json.load(f)
                    temp_f = raw_weather.get("temp")  # Fahrenheit
                    if temp_f is not None:
                        external_temp_f = temp_f
                        external_temp_c = (temp_f - 32) * 5 / 9  # Convert to Celsius
                    humidity = raw_weather.get("relativeHumidity")
                    wind_speed_mph = raw_weather.get("windSpeed")  # mph
                    if wind_speed_mph is not None:
                        wind_speed_ms = wind_speed_mph * 0.44704  # Convert to m/s
                    wind_direction_compass = raw_weather.get(
                        "windDirectionCompassPoint"
                    )

        gear_name = None
        gear_type = None

        if raw_gear_file:
            raw_gear_path = Path(raw_gear_file)
            if raw_gear_path.exists():
                with open(raw_gear_path, encoding="utf-8") as f:
                    raw_gear = json.load(f)
                    if isinstance(raw_gear, list) and len(raw_gear) > 0:
                        gear = raw_gear[0]  # Use first gear item
                        gear_name = gear.get("customMakeModel")
                        gear_type = gear.get("gearTypeName")

        # Determine training_effect_source
        training_effect_source = None
        if training_effect.get("aerobic_te") is not None:
            training_effect_source = "performance_json"

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure activities table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE NOT NULL,
                activity_name VARCHAR,
                start_time_local TIMESTAMP,
                start_time_gmt TIMESTAMP,
                total_time_seconds INTEGER,
                total_distance_km DOUBLE,
                avg_pace_seconds_per_km DOUBLE,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                avg_cadence INTEGER,
                avg_power INTEGER,
                normalized_power INTEGER,
                cadence_stability DOUBLE,
                power_efficiency DOUBLE,
                pace_variability DOUBLE,
                aerobic_te DOUBLE,
                anaerobic_te DOUBLE,
                training_effect_source VARCHAR,
                power_to_weight DOUBLE,
                weight_kg DOUBLE,
                weight_source VARCHAR,
                weight_method VARCHAR,
                stability_score DOUBLE,
                external_temp_c DOUBLE,
                external_temp_f DOUBLE,
                humidity INTEGER,
                wind_speed_ms DOUBLE,
                wind_direction_compass VARCHAR,
                gear_name VARCHAR,
                gear_type VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_elevation_gain DOUBLE,
                total_elevation_loss DOUBLE,
                location_name VARCHAR
            )
            """
        )

        # Delete existing row (upsert behavior)
        conn.execute("DELETE FROM activities WHERE activity_id = ?", [activity_id])

        # Insert activity data
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, date, activity_name, start_time_local, start_time_gmt,
                total_time_seconds, total_distance_km, avg_pace_seconds_per_km,
                avg_heart_rate, max_heart_rate, avg_cadence, avg_power, normalized_power,
                cadence_stability, power_efficiency, pace_variability,
                aerobic_te, anaerobic_te, training_effect_source,
                power_to_weight, weight_kg, weight_source, weight_method, stability_score,
                external_temp_c, external_temp_f, humidity, wind_speed_ms, wind_direction_compass,
                gear_name, gear_type,
                total_elevation_gain, total_elevation_loss, location_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                date,
                activity_name,
                start_time_local,
                start_time_gmt,
                basic_metrics.get("duration_seconds"),
                basic_metrics.get("distance_km"),
                basic_metrics.get("avg_pace_seconds_per_km"),
                basic_metrics.get("avg_heart_rate"),
                basic_metrics.get("max_heart_rate"),
                basic_metrics.get("avg_cadence"),
                basic_metrics.get("avg_power"),
                basic_metrics.get("normalized_power"),
                efficiency_metrics.get("cadence_stability"),
                efficiency_metrics.get("power_efficiency"),
                efficiency_metrics.get("pace_variability"),
                training_effect.get("aerobic_te"),
                training_effect.get("anaerobic_te"),
                training_effect_source,
                power_to_weight.get("watts_per_kg"),
                power_to_weight.get("weight_kg"),
                power_to_weight.get("weight_source"),
                power_to_weight.get("weight_method"),
                power_to_weight.get("stability_score"),
                external_temp_c,
                external_temp_f,
                humidity,
                wind_speed_ms,
                wind_direction_compass,
                gear_name,
                gear_type,
                total_elevation_gain,
                total_elevation_loss,
                location_name,
            ],
        )

        conn.close()

        logger.info(
            f"Successfully inserted activity metadata for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting activity metadata: {e}")
        return False
