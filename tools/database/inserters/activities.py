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
from typing import Any

import duckdb

from tools.utils.paths import get_default_db_path

logger = logging.getLogger(__name__)


def insert_activities(
    activity_id: int,
    date: str,
    db_path: str | None = None,
    raw_activity_file: str | None = None,
    raw_weather_file: str | None = None,
    raw_gear_file: str | None = None,
    conn: Any | None = None,
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
        conn: Optional DuckDB connection (for connection reuse, Phase 5 optimization)

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
                                f"Could not parse startTimeLocal: {start_time_local_str}"
                            )

                    if start_time_gmt_str:
                        try:
                            start_time_gmt = datetime.strptime(
                                start_time_gmt_str, "%Y-%m-%dT%H:%M:%S.%f"
                            )
                        except ValueError:
                            logger.warning(
                                f"Could not parse startTimeGMT: {start_time_gmt_str}"
                            )

        # Load weather data
        temp_celsius = None
        relative_humidity_percent = None
        wind_speed_kmh = None
        wind_direction = None

        if raw_weather_file:
            raw_weather_path = Path(raw_weather_file)
            if raw_weather_path.exists():
                with open(raw_weather_path, encoding="utf-8") as f:
                    raw_weather = json.load(f)
                    temp_celsius = raw_weather.get("temp")
                    relative_humidity_percent = raw_weather.get("relativeHumidity")
                    wind_speed_kmh = raw_weather.get("windSpeed")
                    wind_direction = raw_weather.get("windDirectionCompassPoint")

        # Load gear data
        gear_type = None
        gear_model = None

        if raw_gear_file:
            raw_gear_path = Path(raw_gear_file)
            if raw_gear_path.exists():
                with open(raw_gear_path, encoding="utf-8") as f:
                    raw_gear = json.load(f)
                    gear_type = raw_gear.get("gearTypeName")
                    gear_model = raw_gear.get("customMakeModel")

        # Set default DB path
        if db_path is None:
            db_path = str(get_default_db_path())

        # Phase 5 optimization: Reuse connection if provided
        if conn is not None:
            # Use provided connection (no context manager needed)
            _insert_with_connection(
                conn,
                activity_id,
                date,
                activity_name,
                start_time_local,
                start_time_gmt,
                location_name,
                total_distance_km,
                total_time_seconds,
                avg_speed_ms,
                avg_pace_seconds_per_km,
                avg_heart_rate,
                max_heart_rate,
                temp_celsius,
                relative_humidity_percent,
                wind_speed_kmh,
                wind_direction,
                gear_type,
                gear_model,
            )
        else:
            # Open new connection (backward compatible)
            with duckdb.connect(db_path) as connection:
                _insert_with_connection(
                    connection,
                    activity_id,
                    date,
                    activity_name,
                    start_time_local,
                    start_time_gmt,
                    location_name,
                    total_distance_km,
                    total_time_seconds,
                    avg_speed_ms,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    max_heart_rate,
                    temp_celsius,
                    relative_humidity_percent,
                    wind_speed_kmh,
                    wind_direction,
                    gear_type,
                    gear_model,
                )

        return True

    except Exception as e:
        logger.error(f"Error inserting activity {activity_id}: {e}")
        return False


def _insert_with_connection(
    conn: Any,
    activity_id: int,
    date: str,
    activity_name: str | None,
    start_time_local: datetime | None,
    start_time_gmt: datetime | None,
    location_name: str | None,
    total_distance_km: float | None,
    total_time_seconds: int | None,
    avg_speed_ms: float | None,
    avg_pace_seconds_per_km: float | None,
    avg_heart_rate: int | None,
    max_heart_rate: int | None,
    temp_celsius: float | None,
    relative_humidity_percent: float | None,
    wind_speed_kmh: float | None,
    wind_direction: str | None,
    gear_type: str | None,
    gear_model: str | None,
) -> None:
    """Helper function to insert activity data with a given connection."""
    # Create schema if not exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE NOT NULL,
            activity_name VARCHAR,
            start_time_local TIMESTAMP,
            start_time_gmt TIMESTAMP,
            location_name VARCHAR,
            total_distance_km DOUBLE,
            total_time_seconds INTEGER,
            avg_speed_ms DOUBLE,
            avg_pace_seconds_per_km DOUBLE,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            temp_celsius DOUBLE,
            relative_humidity_percent DOUBLE,
            wind_speed_kmh DOUBLE,
            wind_direction VARCHAR,
            gear_type VARCHAR,
            gear_model VARCHAR
        )
        """
    )

    # Delete existing record (UPSERT semantics)
    conn.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))

    # Insert new record
    conn.execute(
        """
        INSERT INTO activities (
            activity_id,
            activity_date,
            activity_name,
            start_time_local,
            start_time_gmt,
            location_name,
            total_distance_km,
            total_time_seconds,
            avg_speed_ms,
            avg_pace_seconds_per_km,
            avg_heart_rate,
            max_heart_rate,
            temp_celsius,
            relative_humidity_percent,
            wind_speed_kmh,
            wind_direction,
            gear_type,
            gear_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            date,
            activity_name,
            start_time_local,
            start_time_gmt,
            location_name,
            total_distance_km,
            total_time_seconds,
            avg_speed_ms,
            avg_pace_seconds_per_km,
            avg_heart_rate,
            max_heart_rate,
            temp_celsius,
            relative_humidity_percent,
            wind_speed_kmh,
            wind_direction,
            gear_type,
            gear_model,
        ),
    )
