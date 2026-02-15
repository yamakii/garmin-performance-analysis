"""
HeartRateZonesInserter - Insert heart_rate_zones to DuckDB

Inserts heart rate zone data into heart_rate_zones table from raw data (hr_zones.json).
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_heart_rate_zones(
    activity_id: int,
    db_path: str | None = None,
    raw_hr_zones_file: str | None = None,
) -> bool:
    """
    Insert heart_rate_zones into DuckDB heart_rate_zones table.

    Steps:
    1. Load data from raw hr_zones.json
    2. Extract heart_rate_zones
    3. Calculate zone boundaries and percentages
    4. Insert 5 rows (one per zone) into heart_rate_zones table

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_hr_zones_file: Path to raw hr_zones.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_hr_zones_file:
            logger.error("raw_hr_zones_file is required")
            return False

        zones_data = _extract_heart_rate_zones_from_raw(raw_hr_zones_file)
        if not zones_data:
            logger.error(f"Failed to extract heart_rate_zones from {raw_hr_zones_file}")
            return False

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure heart_rate_zones table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heart_rate_zones (
                activity_id BIGINT,
                zone_number INTEGER,
                zone_low_boundary INTEGER,
                zone_high_boundary INTEGER,
                time_in_zone_seconds DOUBLE,
                zone_percentage DOUBLE,
                PRIMARY KEY (activity_id, zone_number)
            )
            """)

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
