"""
SplitsInserter - Insert split_metrics from performance.json to DuckDB splits table

Inserts split-by-split data into splits table for efficient querying and report generation.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_splits(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert split_metrics from performance.json into DuckDB splits table.

    Steps:
    1. Load performance.json
    2. Extract split_metrics array
    3. Insert each split into splits table

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

        # Extract split_metrics
        split_metrics = performance_data.get("split_metrics")
        if not split_metrics or not isinstance(split_metrics, list):
            logger.error(f"No split_metrics found in {performance_file}")
            return False

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure splits table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS splits (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                role_phase VARCHAR,
                pace_str VARCHAR,
                pace_seconds_per_km DOUBLE,
                heart_rate INTEGER,
                hr_zone VARCHAR,
                cadence DOUBLE,
                cadence_rating VARCHAR,
                power DOUBLE,
                power_efficiency VARCHAR,
                stride_length DOUBLE,
                ground_contact_time DOUBLE,
                vertical_oscillation DOUBLE,
                vertical_ratio DOUBLE,
                elevation_gain DOUBLE,
                elevation_loss DOUBLE,
                terrain_type VARCHAR,
                environmental_conditions VARCHAR,
                wind_impact VARCHAR,
                temp_impact VARCHAR,
                environmental_impact VARCHAR,
                PRIMARY KEY (activity_id, split_index)
            )
            """
        )

        # Delete existing splits for this activity (for re-insertion)
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])

        # Insert each split
        for split in split_metrics:
            split_number = split.get("split_number")
            if split_number is None:
                continue

            # Format pace string
            pace_seconds = split.get("avg_pace_seconds_per_km")
            if pace_seconds and pace_seconds > 0:
                minutes = int(pace_seconds // 60)
                seconds = int(pace_seconds % 60)
                pace_str = f"{minutes}:{seconds:02d}"
            else:
                pace_str = None

            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, role_phase, pace_str, pace_seconds_per_km,
                    heart_rate, cadence, power, ground_contact_time,
                    vertical_oscillation, vertical_ratio, elevation_gain,
                    elevation_loss, terrain_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    split_number,
                    split.get("distance_km"),
                    split.get("role_phase"),
                    pace_str,
                    pace_seconds,
                    split.get("avg_heart_rate"),
                    split.get("avg_cadence"),
                    split.get("avg_power"),
                    split.get("ground_contact_time_ms"),
                    split.get("vertical_oscillation_cm"),
                    split.get("vertical_ratio_percent"),
                    split.get("elevation_gain_m"),
                    split.get("elevation_loss_m"),
                    split.get("terrain_type"),
                ],
            )

        conn.close()

        logger.info(
            f"Successfully inserted {len(split_metrics)} splits for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting splits: {e}")
        return False
