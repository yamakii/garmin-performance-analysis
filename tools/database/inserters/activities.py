"""
ActivitiesInserter - Insert activity metadata to DuckDB activities table

Populates the activities table with metadata from raw API files.
This inserter must be called FIRST before other inserters due to foreign key constraints.
Most fields are populated by other inserters; this inserter only handles:
- Activity metadata (name, timestamps, location) from activity.json
- Weather data (temperature, humidity, wind) from weather.json
- Gear data (name, type) from gear.json
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_activities(
    activity_id: int,
    date: str,
    db_path: str | None = None,
    raw_activity_file: str | None = None,
    raw_weather_file: str | None = None,
    raw_gear_file: str | None = None,
) -> bool:
    """
    Insert activity metadata into DuckDB activities table from raw data files.

    Extracts 36 columns from raw API files:
    - activity.json: activityName, startTimeLocal, startTimeGMT, locationName
    - weather.json: temp, relativeHumidity, windSpeed, windDirectionCompassPoint
    - gear.json: gearTypeName, customMakeModel

    Args:
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
        # Raw data mode: Extract from raw files only
        logger.debug(f"Inserting activity {activity_id} from raw data")

        # Load optional raw data files
        activity_name = None
        start_time_local = None
        start_time_gmt = None
        location_name = None
        total_distance_km = None
        total_time_seconds = None
        avg_speed_ms = None
        avg_pace_seconds_per_km = None
        avg_heart_rate = None
        max_heart_rate = None

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

                    # Extract basic metrics from summaryDTO
                    distance_meters = summary_dto.get("distance")
                    if distance_meters is not None:
                        total_distance_km = distance_meters / 1000

                    duration_seconds = summary_dto.get("duration")
                    if duration_seconds is not None:
                        total_time_seconds = int(duration_seconds)

                    avg_speed_ms = summary_dto.get("averageSpeed")
                    if avg_speed_ms is not None and avg_speed_ms > 0:
                        avg_pace_seconds_per_km = 1000 / avg_speed_ms

                    avg_heart_rate = summary_dto.get("averageHR")
                    if avg_heart_rate is not None:
                        avg_heart_rate = int(avg_heart_rate)

                    max_heart_rate = summary_dto.get("maxHR")
                    if max_heart_rate is not None:
                        max_heart_rate = int(max_heart_rate)

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

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

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

        # Use INSERT OR REPLACE for upsert behavior (avoids foreign key constraint issues)
        # Insert activity data (most fields NULL as they come from other inserters)
        conn.execute(
            """
            INSERT OR REPLACE INTO activities (
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
                total_time_seconds,
                total_distance_km,
                avg_pace_seconds_per_km,
                avg_heart_rate,
                max_heart_rate,
                None,  # avg_cadence (populated by other inserters)
                None,  # avg_power (populated by other inserters)
                None,  # normalized_power (populated by other inserters)
                None,  # cadence_stability (populated by other inserters)
                None,  # power_efficiency (populated by other inserters)
                None,  # pace_variability (populated by other inserters)
                None,  # aerobic_te (populated by other inserters)
                None,  # anaerobic_te (populated by other inserters)
                None,  # training_effect_source (populated by other inserters)
                None,  # power_to_weight (populated by other inserters)
                None,  # weight_kg (populated by other inserters)
                None,  # weight_source (populated by other inserters)
                None,  # weight_method (populated by other inserters)
                None,  # stability_score (populated by other inserters)
                external_temp_c,
                external_temp_f,
                humidity,
                wind_speed_ms,
                wind_direction_compass,
                gear_name,
                gear_type,
                None,  # total_elevation_gain (populated by splits inserter)
                None,  # total_elevation_loss (populated by splits inserter)
                location_name,
            ],
        )

        conn.commit()
        conn.close()

        logger.info(
            f"Successfully inserted activity metadata for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting activity metadata: {e}")
        return False
