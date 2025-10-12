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
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert vo2_max from performance.json into DuckDB vo2_max table.

    Steps:
    1. Load performance.json
    2. Extract vo2_max data
    3. Insert into vo2_max table

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
