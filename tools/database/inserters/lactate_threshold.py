"""
LactateThresholdInserter - Insert lactate_threshold from performance.json to DuckDB

Inserts lactate threshold data (HR, speed, power) into lactate_threshold table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_lactate_threshold(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert lactate_threshold from performance.json into DuckDB lactate_threshold table.

    Steps:
    1. Load performance.json
    2. Extract lactate_threshold (speed_and_heart_rate and power)
    3. Insert into lactate_threshold table

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

        # Extract lactate_threshold
        lt_data = performance_data.get("lactate_threshold")
        if not lt_data or not isinstance(lt_data, dict):
            logger.error(f"No lactate_threshold found in {performance_file}")
            return False

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
                speed_hr.get("speed") if speed_hr else None,
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
