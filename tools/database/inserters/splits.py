"""
SplitsInserter - Insert split_metrics to DuckDB splits table

Extracts split-by-split data from raw splits.json and inserts into splits table
for efficient querying and report generation.
"""

import json
import logging
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


def _classify_terrain(elevation_gain: float, elevation_loss: float) -> str:
    """
    Classify terrain type based on elevation changes.

    Args:
        elevation_gain: Elevation gain in meters
        elevation_loss: Elevation loss in meters

    Returns:
        Terrain type classification
    """
    total_elevation_change = abs(elevation_gain) + abs(elevation_loss)

    if total_elevation_change < 5:
        return "平坦"
    elif total_elevation_change < 15:
        return "起伏"
    elif total_elevation_change < 30:
        return "丘陵"
    else:
        return "山岳"


def _map_intensity_to_phase(intensity_type: str | None) -> str | None:
    """
    Map Garmin intensityType to role_phase.

    Args:
        intensity_type: Garmin intensityType (e.g., "WARMUP", "INTERVAL", "RECOVERY", "COOLDOWN")

    Returns:
        role_phase string or None
    """
    if not intensity_type:
        return None

    intensity_upper = intensity_type.upper()

    # Phase mapping
    if intensity_upper == "WARMUP":
        return "warmup"
    elif intensity_upper in ("INTERVAL", "ACTIVE"):
        return "run"
    elif intensity_upper == "RECOVERY":
        return "recovery"
    elif intensity_upper == "COOLDOWN":
        return "cooldown"
    else:
        return None


def _extract_splits_from_raw(raw_splits_file: str) -> list[dict] | None:
    """
    Extract split metrics from raw splits.json.

    Args:
        raw_splits_file: Path to splits.json

    Returns:
        List of split dictionaries matching performance.json split_metrics structure
    """
    splits_path = Path(raw_splits_file)
    if not splits_path.exists():
        logger.error(f"Splits file not found: {raw_splits_file}")
        return None

    with open(splits_path, encoding="utf-8") as f:
        splits_data = json.load(f)

    lap_dtos = splits_data.get("lapDTOs", [])
    if not lap_dtos:
        logger.error("No lapDTOs found in splits.json")
        return None

    splits = []
    cumulative_time = 0

    for lap in lap_dtos:
        lap_index = lap.get("lapIndex")
        if lap_index is None:
            continue

        # Distance (convert m to km)
        distance_m = lap.get("distance", 0)
        distance_km = distance_m / 1000.0 if distance_m else None

        # Duration
        duration_seconds = lap.get("duration")

        # Time range
        start_time_gmt = lap.get("startTimeGMT")
        start_time_s = cumulative_time
        if duration_seconds:
            end_time_s = cumulative_time + round(duration_seconds)
            cumulative_time = end_time_s
        else:
            end_time_s = None

        # Pace (seconds per km)
        if distance_km and distance_km > 0 and duration_seconds:
            pace_seconds_per_km = duration_seconds / distance_km
        else:
            pace_seconds_per_km = None

        # Format pace string
        if pace_seconds_per_km:
            minutes = int(pace_seconds_per_km // 60)
            seconds = int(pace_seconds_per_km % 60)
            pace_str = f"{minutes}:{seconds:02d}"
        else:
            pace_str = None

        # Intensity type and role phase
        intensity_type = lap.get("intensityType")
        role_phase = _map_intensity_to_phase(intensity_type)

        # HR
        avg_hr = lap.get("averageHR")

        # Cadence
        avg_cadence = lap.get("averageRunCadence")

        # Power
        avg_power = lap.get("averagePower")

        # Form metrics
        gct = lap.get("groundContactTime")
        vo = lap.get("verticalOscillation")
        vr = lap.get("verticalRatio")

        # Elevation
        elevation_gain = lap.get("elevationGain", 0)
        elevation_loss = lap.get("elevationLoss", 0)
        terrain_type = _classify_terrain(elevation_gain, elevation_loss)

        # NEW FIELDS (Phase 1): Add 7 missing performance metrics
        stride_length = lap.get("strideLength")  # cm
        max_hr = lap.get("maxHR")  # bpm
        max_cadence = lap.get("maxRunCadence")  # spm
        max_power = lap.get("maxPower")  # W
        normalized_power = lap.get("normalizedPower")  # W
        average_speed = lap.get("averageSpeed")  # m/s
        grade_adjusted_speed = lap.get("avgGradeAdjustedSpeed")  # m/s

        split_dict = {
            "split_number": lap_index,
            "distance_km": distance_km,
            "duration_seconds": duration_seconds,
            "start_time_gmt": start_time_gmt,
            "start_time_s": start_time_s,
            "end_time_s": end_time_s,
            "intensity_type": intensity_type,
            "role_phase": role_phase,
            "pace_str": pace_str,
            "pace_seconds_per_km": pace_seconds_per_km,
            "avg_heart_rate": avg_hr,
            "avg_cadence": avg_cadence,
            "avg_power": avg_power,
            "ground_contact_time_ms": gct,
            "vertical_oscillation_cm": vo,
            "vertical_ratio_percent": vr,
            "elevation_gain_m": elevation_gain,
            "elevation_loss_m": elevation_loss,
            "terrain_type": terrain_type,
            # NEW FIELDS (Phase 1): 7 missing performance metrics
            "stride_length_cm": stride_length,
            "max_heart_rate": max_hr,
            "max_cadence": max_cadence,
            "max_power": max_power,
            "normalized_power": normalized_power,
            "average_speed_mps": average_speed,
            "grade_adjusted_speed_mps": grade_adjusted_speed,
        }

        splits.append(split_dict)

    return splits


def insert_splits(
    activity_id: int,
    db_path: str | None = None,
    raw_splits_file: str | None = None,
    conn: Any | None = None,
) -> bool:
    """
    Insert split_metrics from raw splits.json into DuckDB splits table.

    Steps:
    1. Load raw splits.json
    2. Extract and calculate split_metrics
    3. Insert each split into splits table

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_splits_file: Path to raw splits.json
        conn: Optional DuckDB connection (for connection reuse, Phase 5 optimization)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_splits_file:
            logger.error("raw_splits_file required")
            return False

        split_metrics = _extract_splits_from_raw(raw_splits_file)
        if not split_metrics:
            logger.error("Failed to extract splits from raw data")
            return False

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Phase 5 optimization: Reuse connection if provided
        if conn is not None:
            # Use provided connection (no close needed)
            _insert_splits_with_connection(conn, activity_id, split_metrics)
        else:
            # Open new connection (backward compatible)
            connection = duckdb.connect(str(db_path))
            try:
                _insert_splits_with_connection(connection, activity_id, split_metrics)
            finally:
                connection.close()

        logger.info(
            f"Successfully inserted {len(split_metrics)} splits for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting splits: {e}")
        return False


def _insert_splits_with_connection(
    conn: Any, activity_id: int, split_metrics: list[dict]
) -> None:
    """Helper function to insert splits with a given connection."""
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

    # Add 6 new columns (Phase 1 - stride_length already exists in schema)
    # Use IF NOT EXISTS for idempotency
    try:
        conn.execute(
            "ALTER TABLE splits ADD COLUMN IF NOT EXISTS max_heart_rate INTEGER"
        )
    except Exception:
        pass  # Column may already exist

    try:
        conn.execute("ALTER TABLE splits ADD COLUMN IF NOT EXISTS max_cadence DOUBLE")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE splits ADD COLUMN IF NOT EXISTS max_power DOUBLE")
    except Exception:
        pass

    try:
        conn.execute(
            "ALTER TABLE splits ADD COLUMN IF NOT EXISTS normalized_power DOUBLE"
        )
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE splits ADD COLUMN IF NOT EXISTS average_speed DOUBLE")
    except Exception:
        pass

    try:
        conn.execute(
            "ALTER TABLE splits ADD COLUMN IF NOT EXISTS grade_adjusted_speed DOUBLE"
        )
    except Exception:
        pass

    # Delete existing splits for this activity (for re-insertion)
    conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])

    # Insert each split with 7 new fields
    for split in split_metrics:
        split_number = split.get("split_number")
        if split_number is None:
            continue

        conn.execute(
            """
            INSERT INTO splits (
                activity_id, split_index, distance,
                duration_seconds, start_time_gmt, start_time_s, end_time_s, intensity_type,
                role_phase, pace_str, pace_seconds_per_km,
                heart_rate, cadence, power, ground_contact_time,
                vertical_oscillation, vertical_ratio, elevation_gain,
                elevation_loss, terrain_type,
                stride_length, max_heart_rate, max_cadence, max_power,
                normalized_power, average_speed, grade_adjusted_speed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                split_number,
                split.get("distance_km"),
                split.get("duration_seconds"),
                split.get("start_time_gmt"),
                split.get("start_time_s"),
                split.get("end_time_s"),
                split.get("intensity_type"),
                split.get("role_phase"),
                split.get("pace_str"),
                split.get("pace_seconds_per_km")
                or split.get("avg_pace_seconds_per_km"),
                split.get("avg_heart_rate"),
                split.get("avg_cadence"),
                split.get("avg_power"),
                split.get("ground_contact_time_ms"),
                split.get("vertical_oscillation_cm"),
                split.get("vertical_ratio_percent"),
                split.get("elevation_gain_m"),
                split.get("elevation_loss_m"),
                split.get("terrain_type"),
                # NEW FIELDS (Phase 1): 7 missing performance metrics
                split.get("stride_length_cm"),
                split.get("max_heart_rate"),
                split.get("max_cadence"),
                split.get("max_power"),
                split.get("normalized_power"),
                split.get("average_speed_mps"),
                split.get("grade_adjusted_speed_mps"),
            ],
        )
