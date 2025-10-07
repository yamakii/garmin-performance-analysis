"""
HREfficiencyInserter - Insert hr_efficiency_analysis from performance.json to DuckDB

Inserts heart rate efficiency analysis into hr_efficiency table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_hr_efficiency(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert hr_efficiency_analysis from performance.json into DuckDB hr_efficiency table.

    Steps:
    1. Load performance.json
    2. Extract hr_efficiency_analysis
    3. Insert into hr_efficiency table

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

        # Extract hr_efficiency_analysis
        hr_eff = performance_data.get("hr_efficiency_analysis")
        if not hr_eff or not isinstance(hr_eff, dict):
            logger.error(f"No hr_efficiency_analysis found in {performance_file}")
            return False

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure hr_efficiency table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hr_efficiency (
                activity_id BIGINT PRIMARY KEY,
                primary_zone VARCHAR,
                zone_distribution_rating VARCHAR,
                hr_stability VARCHAR,
                aerobic_efficiency VARCHAR,
                training_quality VARCHAR,
                zone2_focus BOOLEAN,
                zone4_threshold_work BOOLEAN,
                training_type VARCHAR,
                zone1_percentage DOUBLE,
                zone2_percentage DOUBLE,
                zone3_percentage DOUBLE,
                zone4_percentage DOUBLE,
                zone5_percentage DOUBLE
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute("DELETE FROM hr_efficiency WHERE activity_id = ?", [activity_id])

        # Insert hr_efficiency data
        # Note: Current performance.json only has basic fields, others are NULL
        conn.execute(
            """
            INSERT INTO hr_efficiency (
                activity_id,
                hr_stability,
                training_type
            ) VALUES (?, ?, ?)
            """,
            [
                activity_id,
                hr_eff.get("hr_stability"),
                hr_eff.get("training_type"),
            ],
        )

        conn.close()

        logger.info(
            f"Successfully inserted HR efficiency data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting HR efficiency: {e}")
        return False
