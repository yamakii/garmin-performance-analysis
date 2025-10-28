"""
LactateThresholdInserter - Insert lactate_threshold to DuckDB

Inserts lactate threshold data (HR, speed, power) from raw API file
(lactate_threshold.json) into lactate_threshold table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_lactate_threshold(
    activity_id: int,
    db_path: str | None = None,
    raw_lactate_threshold_file: str | None = None,
) -> bool:
    """
    Insert lactate_threshold into DuckDB lactate_threshold table from raw API file.

    Extracts lactate threshold data (HR, speed, power) from lactate_threshold.json
    and inserts into lactate_threshold table.

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_lactate_threshold_file: Path to raw lactate_threshold.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_lactate_threshold_file:
            logger.warning(
                f"No raw_lactate_threshold_file provided for activity {activity_id}, skipping"
            )
            return True  # Not an error, lactate threshold is optional

        lt_data = _extract_lactate_threshold_from_raw(raw_lactate_threshold_file)
        if not lt_data:
            logger.warning(
                f"Failed to extract lactate_threshold from {raw_lactate_threshold_file}, skipping"
            )
            return True  # Not an error, lactate threshold is optional

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure lactate_threshold table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lactate_threshold (
                activity_id BIGINT PRIMARY KEY,
                heart_rate INTEGER,
                speed_mps DOUBLE,
                date_hr TIMESTAMP,
                functional_threshold_power INTEGER,
                power_to_weight DOUBLE,
                weight DOUBLE,
                date_power TIMESTAMP
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM lactate_threshold WHERE activity_id = ?", [activity_id]
        )

        # Extract speed_and_heart_rate data
        speed_hr = lt_data.get("speed_and_heart_rate", {})
        power = lt_data.get("power", {})

        # Parse timestamps (format: "2025-09-12T20:04:58.947")
        date_hr = speed_hr.get("calendarDate") if speed_hr else None
        date_power = power.get("calendarDate") if power else None

        # Convert speed from s/m (seconds per meter) to m/s (meters per second)
        # Garmin API returns pace (s/m), but we store speed (m/s)
        raw_speed = speed_hr.get("speed") if speed_hr else None
        speed_mps = (1.0 / raw_speed) if raw_speed else None

        # Insert lactate threshold data
        conn.execute(
            """
            INSERT INTO lactate_threshold (
                activity_id,
                heart_rate,
                speed_mps,
                date_hr,
                functional_threshold_power,
                power_to_weight,
                weight,
                date_power
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                speed_hr.get("heartRate") if speed_hr else None,
                speed_mps,
                date_hr,
                power.get("functionalThresholdPower") if power else None,
                power.get("powerToWeight") if power else None,
                power.get("weight") if power else None,
                date_power,
            ],
        )

        conn.close()

        logger.info(
            f"Successfully inserted lactate threshold data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting lactate threshold: {e}")
        return False


def _extract_lactate_threshold_from_raw(raw_lactate_threshold_file: str) -> dict | None:
    """
    Extract lactate threshold data from raw lactate_threshold.json.

    Args:
        raw_lactate_threshold_file: Path to raw lactate_threshold.json

    Returns:
        Dict with speed_and_heart_rate and power data, or None if extraction fails
    """
    try:
        raw_path = Path(raw_lactate_threshold_file)
        if not raw_path.exists():
            logger.error(
                f"Raw lactate threshold file not found: {raw_lactate_threshold_file}"
            )
            return None

        with open(raw_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        # Validate structure
        if not isinstance(raw_data, dict):
            logger.error("Invalid lactate threshold data structure")
            return None

        # Extract speed_and_heart_rate and power
        # Raw data already has the correct structure
        return {
            "speed_and_heart_rate": raw_data.get("speed_and_heart_rate"),
            "power": raw_data.get("power"),
        }

    except Exception as e:
        logger.error(f"Error extracting lactate threshold from raw data: {e}")
        return None
