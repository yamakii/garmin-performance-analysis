"""
VO2MaxInserter - Insert vo2_max from performance.json to DuckDB

Inserts VO2 max data (precise value, rounded value, date, fitness age, category) into vo2_max table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_vo2_max(
    performance_file: str | None,
    activity_id: int,
    db_path: str | None = None,
    raw_vo2_max_file: str | None = None,
) -> bool:
    """
    Insert vo2_max into DuckDB vo2_max table.

    Supports two modes:
    1. Legacy mode: Read from performance.json (performance_file provided)
    2. Raw data mode: Read from vo2_max.json (performance_file=None, raw_vo2_max_file provided)

    Steps:
    1. Load data (from performance.json OR raw vo2_max.json)
    2. Extract vo2_max data
    3. Insert into vo2_max table

    Args:
        performance_file: Path to performance.json (legacy mode) or None (raw data mode)
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_vo2_max_file: Path to raw vo2_max.json (raw data mode only)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Determine mode
        use_raw_data = performance_file is None

        if use_raw_data:
            # NEW: Extract from raw data
            if not raw_vo2_max_file:
                logger.error("raw_vo2_max_file required when performance_file is None")
                return False

            vo2_data = _extract_vo2_max_from_raw(raw_vo2_max_file)
            if not vo2_data:
                logger.error(f"Failed to extract vo2_max from {raw_vo2_max_file}")
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

            # Extract vo2_max
            vo2_data = performance_data.get("vo2_max")
            if not vo2_data or not isinstance(vo2_data, dict):
                logger.error(f"No vo2_max found in {performance_file}")
                return False

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure vo2_max table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vo2_max (
                activity_id BIGINT PRIMARY KEY,
                precise_value DOUBLE,
                value DOUBLE,
                date DATE,
                fitness_age INTEGER,
                category INTEGER
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute("DELETE FROM vo2_max WHERE activity_id = ?", [activity_id])

        # Insert vo2_max data
        conn.execute(
            """
            INSERT INTO vo2_max (
                activity_id,
                precise_value,
                value,
                date,
                fitness_age,
                category
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                vo2_data.get("precise_value"),
                vo2_data.get("value"),
                vo2_data.get("date"),
                vo2_data.get("fitness_age"),
                vo2_data.get("category"),
            ],
        )

        conn.close()

        logger.info(f"Successfully inserted vo2_max data for activity {activity_id}")
        return True

    except Exception as e:
        logger.error(f"Error inserting vo2_max: {e}")
        return False


def _extract_vo2_max_from_raw(raw_vo2_max_file: str) -> dict | None:
    """
    Extract vo2_max data from raw API response (vo2_max.json).

    Raw data structure:
    {
        "generic": {
            "vo2MaxValue": 45,
            "vo2MaxPreciseValue": 44.7,
            "calendarDate": "2025-08-19",
            "fitnessAge": null
        }
    }

    Args:
        raw_vo2_max_file: Path to raw vo2_max.json file

    Returns:
        Dict with vo2_max data (keys: precise_value, value, date, fitness_age, category)
        None if file not found or no data
    """
    try:
        raw_path = Path(raw_vo2_max_file)
        if not raw_path.exists():
            logger.warning(f"Raw vo2_max file not found: {raw_vo2_max_file}")
            return None

        with open(raw_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        # Extract from "generic" section
        generic = raw_data.get("generic", {})
        if not generic:
            logger.warning(f"No 'generic' section in {raw_vo2_max_file}")
            return None

        # Map raw API fields to performance.json format
        return {
            "precise_value": generic.get("vo2MaxPreciseValue"),
            "value": (
                float(generic.get("vo2MaxValue"))
                if generic.get("vo2MaxValue") is not None
                else None
            ),
            "date": generic.get("calendarDate"),
            "fitness_age": generic.get("fitnessAge"),
            "category": 0,  # Default category (not provided in raw data)
        }

    except Exception as e:
        logger.error(f"Error extracting vo2_max from raw data: {e}")
        return None
