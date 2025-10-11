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
    raw_splits_file: str | None = None,
) -> bool:
    """
    Insert split_metrics from performance.json into DuckDB splits table.

    Steps:
    1. Load performance.json
    2. Extract split_metrics array
    3. Load raw splits.json (if provided) for time range data
    4. Match lapDTOs with split_metrics by lapIndex/split_number
    5. Calculate cumulative time for start_time_s/end_time_s
    6. Insert each split into splits table

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_splits_file: Optional path to raw splits.json for time range data

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

        # Load raw splits.json if provided
        lap_dtos = []
        if raw_splits_file:
            raw_splits_path = Path(raw_splits_file)
            if raw_splits_path.exists():
                with open(raw_splits_path, encoding="utf-8") as f:
                    raw_splits_data = json.load(f)
                    lap_dtos = raw_splits_data.get("lapDTOs", [])
            else:
                logger.warning(f"Raw splits file not found: {raw_splits_file}")

        # Create lapIndex -> lapDTO mapping
        lap_dto_map = {lap.get("lapIndex"): lap for lap in lap_dtos}

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure splits table exists with new columns
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS splits (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                duration_seconds DOUBLE,
                start_time_gmt VARCHAR,
                start_time_s INTEGER,
                end_time_s INTEGER,
                intensity_type VARCHAR,
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

        # Calculate cumulative time for each split
        cumulative_time = 0

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

            # Get time range data from raw splits.json (if available)
            lap_dto = lap_dto_map.get(split_number)
            duration_seconds = None
            start_time_gmt = None
            intensity_type = None

            if lap_dto:
                duration_seconds = lap_dto.get("duration")
                start_time_gmt = lap_dto.get("startTimeGMT")
                intensity_type = lap_dto.get("intensityType")

            # Calculate start_time_s and end_time_s
            start_time_s = cumulative_time
            if duration_seconds:
                end_time_s = cumulative_time + round(duration_seconds)
                cumulative_time = end_time_s
            else:
                end_time_s = None

            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance,
                    duration_seconds, start_time_gmt, start_time_s, end_time_s, intensity_type,
                    role_phase, pace_str, pace_seconds_per_km,
                    heart_rate, cadence, power, ground_contact_time,
                    vertical_oscillation, vertical_ratio, elevation_gain,
                    elevation_loss, terrain_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    split_number,
                    split.get("distance_km"),
                    duration_seconds,
                    start_time_gmt,
                    start_time_s,
                    end_time_s,
                    intensity_type,
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
