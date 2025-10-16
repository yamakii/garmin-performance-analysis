"""
VO2MaxInserter - Insert vo2_max to DuckDB

Inserts VO2 max data (precise value, rounded value, date, fitness age, category)
from raw API file (vo2_max.json) into vo2_max table.
"""

import json
import logging
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


def insert_vo2_max(
    activity_id: int,
    db_path: str | None = None,
    raw_vo2_max_file: str | None = None,
    conn: Any | None = None,
) -> bool:
    """
    Insert vo2_max into DuckDB vo2_max table from raw API file.

    Extracts VO2 max data (precise value, rounded value, date, fitness age, category)
    from vo2_max.json and inserts into vo2_max table.

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_vo2_max_file: Path to raw vo2_max.json
        conn: Optional DuckDB connection (for connection reuse, Phase 5 optimization)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_vo2_max_file:
            logger.warning(
                f"No raw_vo2_max_file provided for activity {activity_id}, skipping"
            )
            return True  # Not an error, vo2_max is optional

        vo2_data = _extract_vo2_max_from_raw(raw_vo2_max_file)
        if not vo2_data:
            logger.warning(
                f"Failed to extract vo2_max from {raw_vo2_max_file}, skipping"
            )
            return True  # Not an error, vo2_max is optional

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Phase 5 optimization: Reuse connection if provided
        if conn is not None:
            _insert_vo2_max_with_connection(conn, activity_id, vo2_data)
        else:
            # Open new connection (backward compatible)
            connection = duckdb.connect(str(db_path))
            try:
                _insert_vo2_max_with_connection(connection, activity_id, vo2_data)
            finally:
                connection.close()

        logger.info(f"Successfully inserted vo2_max data for activity {activity_id}")
        return True

    except Exception as e:
        logger.error(f"Error inserting vo2_max: {e}")
        return False


def _insert_vo2_max_with_connection(
    conn: Any, activity_id: int, vo2_data: dict
) -> None:
    """Helper function to insert vo2_max data with a given connection."""
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

        # Handle array format from API (e.g., [{...}])
        if isinstance(raw_data, list):
            if not raw_data:
                logger.warning(f"Empty vo2_max data in {raw_vo2_max_file}")
                return None
            raw_data = raw_data[0]  # Get first element

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
