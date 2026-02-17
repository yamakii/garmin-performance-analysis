"""
SplitsInserter - Insert split_metrics to DuckDB splits table

Extracts split-by-split data from raw splits.json and inserts into splits table
for efficient querying and report generation.

Helper logic has been extracted to splits_helpers/ package:
- TerrainClassifier: Terrain classification
- PhaseMapper: Intensity type mapping and estimation
- HRCalculator: Heart rate zone calculation
- CadencePowerCalculator: Cadence and power metrics
- EnvironmentalCalculator: Environmental conditions
- SplitsExtractor: Raw data extraction
"""

import logging

import duckdb

from garmin_mcp.database.inserters.splits_helpers.extractor import SplitsExtractor
from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper

logger = logging.getLogger(__name__)


def insert_splits(
    activity_id: int,
    conn: duckdb.DuckDBPyConnection,
    raw_splits_file: str | None = None,
) -> bool:
    """
    Insert split_metrics from raw splits.json into DuckDB splits table.

    Steps:
    1. Load raw splits.json
    2. Extract and calculate split_metrics
    3. Insert each split into splits table

    Args:
        activity_id: Activity ID
        conn: DuckDB connection
        raw_splits_file: Path to raw splits.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_splits_file:
            logger.error("raw_splits_file required")
            return False

        split_metrics = SplitsExtractor.extract_splits_from_raw(raw_splits_file)
        if not split_metrics:
            logger.error("Failed to extract splits from raw data")
            return False

        _insert_splits_with_connection(conn, activity_id, split_metrics)

        logger.info(
            f"Successfully inserted {len(split_metrics)} splits for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting splits: {e}")
        return False


def _insert_splits_with_connection(
    conn: duckdb.DuckDBPyConnection, activity_id: int, split_metrics: list[dict]
) -> None:
    """Helper function to insert splits with a given connection."""
    # Delete existing splits for this activity (for re-insertion)
    conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])

    # Apply intensity_type estimation for NULL values (Feature: #40)
    # Check if any splits have NULL intensity_type
    has_null_intensity = any(
        split.get("intensity_type") is None for split in split_metrics
    )

    if has_null_intensity:
        logger.info(
            f"Estimating intensity_type for activity {activity_id} (found NULL values)"
        )

        # Get estimated intensity types for all splits
        estimated_types = PhaseMapper.estimate_intensity_type(split_metrics)

        # Apply estimation only to splits with NULL intensity_type
        for split, estimated_type in zip(split_metrics, estimated_types, strict=True):
            if split.get("intensity_type") is None:
                split["intensity_type"] = estimated_type

        logger.info(
            f"Applied intensity_type estimation for activity {activity_id}: {estimated_types}"
        )

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
