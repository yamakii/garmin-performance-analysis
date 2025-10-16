"""
HeartRateZonesInserter - Insert heart_rate_zones to DuckDB

Supports both legacy (performance.json) and raw data modes (hr_zones.json)

Inserts heart rate zone data into heart_rate_zones table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_heart_rate_zones(
    performance_file: str | None,
    activity_id: int,
    db_path: str | None = None,
    raw_hr_zones_file: str | None = None,
) -> bool:
    """
    Insert heart_rate_zones into DuckDB heart_rate_zones table.

    Supports two modes:
    1. Legacy mode: Read from performance.json (performance_file provided)
    2. Raw data mode: Read from hr_zones.json (performance_file=None, raw_hr_zones_file provided)

    Steps:
    1. Load data (from performance.json OR raw hr_zones.json)
    2. Extract heart_rate_zones
    3. Calculate zone boundaries and percentages
    4. Insert 5 rows (one per zone) into heart_rate_zones table

    Args:
        performance_file: Path to performance.json (legacy mode) or None (raw data mode)
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_hr_zones_file: Path to raw hr_zones.json (raw data mode only)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Determine mode
        use_raw_data = performance_file is None

        if use_raw_data:
            # NEW: Extract from raw data
            if not raw_hr_zones_file:
                logger.error("raw_hr_zones_file required when performance_file is None")
                return False

            zones_data = _extract_heart_rate_zones_from_raw(raw_hr_zones_file)
            if not zones_data:
                logger.error(
                    f"Failed to extract heart_rate_zones from {raw_hr_zones_file}"
                )
                return False
        else:
            # LEGACY: Read from performance.json
            if not performance_file:
                logger.error("performance_file required when not using raw data mode")
                return False

            performance_path = Path(performance_file)
            if not performance_path.exists():
                logger.error(f"Performance file not found: {performance_file}")
                return False

            with open(performance_path, encoding="utf-8") as f:
                performance_data = json.load(f)

            # Extract heart_rate_zones
            hr_zones = performance_data.get("heart_rate_zones")
            if not hr_zones or not isinstance(hr_zones, dict):
                logger.error(f"No heart_rate_zones found in {performance_file}")
                return False

            # Get total duration for percentage calculation
            basic_metrics = performance_data.get("basic_metrics", {})
            total_duration = basic_metrics.get("duration_seconds", 0)
            if total_duration == 0:
                logger.error(f"No duration_seconds found in {performance_file}")
                return False

            # Convert legacy format to zones_data format
            zones_data = []
            for zone_num in range(1, 6):
                zone_key = f"zone{zone_num}"
                zone_data = hr_zones.get(zone_key, {})

                low_boundary = zone_data.get("low")
                time_in_zone = zone_data.get("secs_in_zone", 0.0)

                # Calculate high boundary (next zone's low - 1, or max HR for zone 5)
                if zone_num < 5:
                    next_zone_key = f"zone{zone_num + 1}"
                    high_boundary = hr_zones.get(next_zone_key, {}).get("low", 220) - 1
                else:
                    high_boundary = 220  # Typical max HR

                # Calculate percentage
                zone_percentage = (
                    (time_in_zone / total_duration * 100) if total_duration > 0 else 0.0
                )

                zones_data.append(
                    {
                        "zone_number": zone_num,
                        "low_boundary": low_boundary,
                        "high_boundary": high_boundary,
                        "time_in_zone": time_in_zone,
                        "percentage": zone_percentage,
                    }
                )

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure heart_rate_zones table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heart_rate_zones (
                activity_id BIGINT,
                zone_number INTEGER,
                zone_low_boundary INTEGER,
                zone_high_boundary INTEGER,
                time_in_zone_seconds DOUBLE,
                zone_percentage DOUBLE,
                PRIMARY KEY (activity_id, zone_number)
            )
            """
        )

        # Delete existing records for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM heart_rate_zones WHERE activity_id = ?", [activity_id]
        )

        # Insert all zones
        for zone in zones_data:
            conn.execute(
                """
                INSERT INTO heart_rate_zones (
                    activity_id,
                    zone_number,
                    zone_low_boundary,
                    zone_high_boundary,
                    time_in_zone_seconds,
                    zone_percentage
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    zone["zone_number"],
                    zone["low_boundary"],
                    zone["high_boundary"],
                    zone["time_in_zone"],
                    zone["percentage"],
                ],
            )

        conn.close()

        logger.info(
            f"Successfully inserted heart rate zones data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting heart rate zones: {e}")
        return False


def _extract_heart_rate_zones_from_raw(
    raw_hr_zones_file: str,
) -> list[dict] | None:
    """
    Extract heart rate zones data from raw hr_zones.json.

    Args:
        raw_hr_zones_file: Path to raw hr_zones.json

    Returns:
        List of zone dicts with calculated boundaries and percentages, or None if extraction fails
    """
    try:
        raw_path = Path(raw_hr_zones_file)
        if not raw_path.exists():
            logger.error(f"Raw HR zones file not found: {raw_hr_zones_file}")
            return None

        with open(raw_path, encoding="utf-8") as f:
            raw_zones = json.load(f)

        # Validate structure (should be a list)
        if not isinstance(raw_zones, list):
            logger.error("Invalid HR zones data structure (expected list)")
            return None

        # Calculate total duration
        total_duration = sum(zone.get("secsInZone", 0) for zone in raw_zones)
        if total_duration == 0:
            logger.warning("Total duration is 0, zone percentages will be 0")

        # Extract and transform zones
        zones_data = []
        for zone in raw_zones:
            zone_num = zone.get("zoneNumber")
            if zone_num is None:
                continue

            low_boundary = zone.get("zoneLowBoundary")
            time_in_zone = zone.get("secsInZone", 0.0)

            # Calculate high boundary (next zone's low - 1, or max HR for zone 5)
            if zone_num < 5:
                # Find next zone
                next_zone = next(
                    (z for z in raw_zones if z.get("zoneNumber") == zone_num + 1), None
                )
                high_boundary = (
                    next_zone.get("zoneLowBoundary", 220) - 1 if next_zone else 220
                )
            else:
                high_boundary = 220  # Typical max HR

            # Calculate percentage
            zone_percentage = (
                (time_in_zone / total_duration * 100) if total_duration > 0 else 0.0
            )

            zones_data.append(
                {
                    "zone_number": zone_num,
                    "low_boundary": low_boundary,
                    "high_boundary": high_boundary,
                    "time_in_zone": time_in_zone,
                    "percentage": zone_percentage,
                }
            )

        return zones_data

    except Exception as e:
        logger.error(f"Error extracting heart rate zones from raw data: {e}")
        return None
