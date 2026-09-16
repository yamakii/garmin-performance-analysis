"""
ActivitiesInserter - Insert activity metadata to DuckDB activities table

Populates the activities table with metadata from raw API files.
This inserter must be called FIRST before other inserters due to foreign key constraints.
Most fields are populated by other inserters; this inserter only handles:
- Activity metadata (name, timestamps, location) from activity.json
- Weather data (temperature, humidity, wind) from weather.json
- Gear data (type, model, nickname, uuid) from gear.json
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb

from garmin_mcp.validation.validators import validate_activity

logger = logging.getLogger(__name__)


def _gear_max_km(maximum_meters: object) -> float | None:
    """Convert gear.json ``maximumMeters`` to km, or None when absent/unusable.

    A zero limit means "no limit set" in Garmin, so it is treated as unknown
    rather than as a shoe that is instantly worn out.
    """
    if not isinstance(maximum_meters, int | float) or isinstance(maximum_meters, bool):
        return None
    if maximum_meters <= 0:
        return None
    return round(float(maximum_meters) / 1000.0, 1)


def _gear_date(value: object) -> str | None:
    """Take the date half of a gear.json timestamp (``2026-09-08T00:00:00.0``)."""
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


def insert_activities(
    activity_id: int,
    date: str,
    conn: duckdb.DuckDBPyConnection,
    raw_activity_file: str | None = None,
    raw_weather_file: str | None = None,
    raw_gear_file: str | None = None,
    base_weight_kg: float | None = None,
) -> bool:
    """
    Insert activity metadata into DuckDB activities table from raw data files.

    Extracts 36 columns from raw API files:
    - activity.json: activityName, startTimeLocal, startTimeGMT, locationName
    - weather.json: temp, relativeHumidity, windSpeed, windDirectionCompassPoint
    - gear.json: gearTypeName, customMakeModel, displayName, uuid

    Args:
        activity_id: Activity ID
        date: Activity date (YYYY-MM-DD format)
        conn: DuckDB connection
        raw_activity_file: Optional path to raw activity.json
        raw_weather_file: Optional path to raw weather.json
        raw_gear_file: Optional path to raw gear.json
        base_weight_kg: Optional 7-day median weight for W/kg calculation

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
                    # Skip non-running activities
                    activity_type_dto = raw_activity.get("activityTypeDTO", {})
                    activity_type_key = activity_type_dto.get("typeKey", "")
                    running_type_keys = {"running", "treadmill_running"}
                    if activity_type_key not in running_type_keys:
                        logger.info(
                            f"Skipping non-running activity {activity_id}: "
                            f"type={activity_type_key}"
                        )
                        return False

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
                    # Convert Fahrenheit to Celsius
                    temp_fahrenheit = raw_weather.get("temp")
                    temp_celsius = (
                        (temp_fahrenheit - 32) * 5 / 9
                        if temp_fahrenheit is not None
                        else None
                    )
                    relative_humidity_percent = raw_weather.get("relativeHumidity")
                    wind_speed_kmh = raw_weather.get("windSpeed")
                    wind_direction = raw_weather.get("windDirectionCompassPoint")

        # Load gear data
        gear_type = None
        gear_model = None
        gear_nickname = None
        gear_uuid = None
        gear_max_km = None
        gear_status = None
        gear_since_date = None
        gear_retired_date = None

        if raw_gear_file:
            raw_gear_path = Path(raw_gear_file)
            if raw_gear_path.exists():
                with open(raw_gear_path, encoding="utf-8") as f:
                    raw_gear = json.load(f)
                    # Handle both list and dict formats
                    if isinstance(raw_gear, list) and len(raw_gear) > 0:
                        gear_data = raw_gear[0]  # First item in list
                    elif isinstance(raw_gear, dict):
                        gear_data = raw_gear
                    else:
                        gear_data = None

                    if gear_data:
                        gear_type = gear_data.get("gearTypeName")
                        gear_model = gear_data.get("customMakeModel")
                        # Garmin's newer gear form leaves customMakeModel as the
                        # base model name, so successive generations of the same
                        # shoe collide on it. displayName is the athlete's own
                        # nickname (e.g. "v15") and uuid is stable per pair, so
                        # both are kept: uuid identifies, nickname names.
                        gear_nickname = gear_data.get("displayName")
                        gear_uuid = gear_data.get("uuid")
                        # Lifecycle snapshot as of this ingest (#1209). The
                        # replacement limit is the athlete's own setting, so it
                        # beats any generic mileage rule; status / dates can
                        # change for the same pair over time, which is why a
                        # reader takes them from the shoe's newest activity.
                        gear_max_km = _gear_max_km(gear_data.get("maximumMeters"))
                        gear_status = gear_data.get("gearStatusName")
                        gear_since_date = _gear_date(gear_data.get("dateBegin"))
                        gear_retired_date = _gear_date(gear_data.get("dateEnd"))

        # Validate before insertion
        validate_activity(
            {
                "activity_id": activity_id,
                "activity_date": date,
                "activity_name": activity_name,
                "total_distance_km": total_distance_km,
                "total_time_seconds": total_time_seconds,
                "avg_speed_ms": avg_speed_ms,
                "avg_pace_seconds_per_km": avg_pace_seconds_per_km,
                "avg_heart_rate": avg_heart_rate,
                "max_heart_rate": max_heart_rate,
                "temp_celsius": temp_celsius,
                "relative_humidity_percent": relative_humidity_percent,
                "wind_speed_kmh": wind_speed_kmh,
                "wind_direction": wind_direction,
                "gear_type": gear_type,
                "gear_model": gear_model,
                "gear_nickname": gear_nickname,
                "gear_uuid": gear_uuid,
                "gear_max_km": gear_max_km,
                "gear_status": gear_status,
                "gear_since_date": gear_since_date,
                "gear_retired_date": gear_retired_date,
                "base_weight_kg": base_weight_kg,
            }
        )

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
            gear_nickname,
            gear_uuid,
            gear_max_km,
            gear_status,
            gear_since_date,
            gear_retired_date,
            base_weight_kg,
        )

        return True

    except Exception as e:
        logger.error(f"Error inserting activity {activity_id}: {e}")
        return False


def _insert_with_connection(
    conn: duckdb.DuckDBPyConnection,
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
    gear_nickname: str | None,
    gear_uuid: str | None,
    gear_max_km: float | None,
    gear_status: str | None,
    gear_since_date: str | None,
    gear_retired_date: str | None,
    base_weight_kg: float | None,
) -> None:
    """Helper function to insert activity data with a given connection."""
    # Schema is created by GarminDBWriter.create_schema()

    # Insert or replace record (UPSERT semantics)
    conn.execute(
        """
        INSERT OR REPLACE INTO activities (
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
            gear_model,
            gear_nickname,
            gear_uuid,
            gear_max_km,
            gear_status,
            gear_since_date,
            gear_retired_date,
            base_weight_kg
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            gear_nickname,
            gear_uuid,
            gear_max_km,
            gear_status,
            gear_since_date,
            gear_retired_date,
            base_weight_kg,
        ),
    )
