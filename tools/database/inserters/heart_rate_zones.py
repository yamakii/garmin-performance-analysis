"""
HeartRateZonesInserter - Insert heart_rate_zones from performance.json to DuckDB

Inserts heart rate zone data into heart_rate_zones table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_heart_rate_zones(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert heart_rate_zones from performance.json into DuckDB heart_rate_zones table.

    Steps:
    1. Load performance.json
    2. Extract heart_rate_zones
    3. Calculate zone boundaries and percentages
    4. Insert 5 rows (one per zone) into heart_rate_zones table

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)

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

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

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

        # Extract zone data and calculate boundaries
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
