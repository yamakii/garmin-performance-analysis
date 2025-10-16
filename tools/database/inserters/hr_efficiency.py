"""
HREfficiencyInserter - Insert hr_efficiency_analysis from performance.json to DuckDB

Inserts heart rate efficiency analysis into hr_efficiency table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def _extract_hr_efficiency_from_raw(
    hr_zones_file: str | None, activity_file: str | None
) -> dict:
    """
    Extract HR efficiency data from raw hr_zones.json and activity.json files.

    Args:
        hr_zones_file: Path to hr_zones.json
        activity_file: Path to activity.json

    Returns:
        Dictionary with hr_efficiency data matching performance.json structure
    """
    if not hr_zones_file or not activity_file:
        logger.error("Both hr_zones_file and activity_file required for raw mode")
        return {}

    # Explicit type narrowing for mypy
    assert hr_zones_file is not None
    assert activity_file is not None

    hr_zones_path = Path(hr_zones_file)
    activity_path = Path(activity_file)

    if not hr_zones_path.exists():
        logger.error(f"HR zones file not found: {hr_zones_file}")
        return {}

    if not activity_path.exists():
        logger.error(f"Activity file not found: {activity_file}")
        return {}

    # Load hr_zones.json
    with open(hr_zones_path, encoding="utf-8") as f:
        hr_zones = json.load(f)

    # Load activity.json for training_effect_label
    with open(activity_path, encoding="utf-8") as f:
        activity_data = json.load(f)

    summary_dto = activity_data.get("summaryDTO", {})
    training_effect_label = summary_dto.get("trainingEffectLabel")

    # Calculate zone percentages
    total_time = sum(zone.get("secsInZone", 0) for zone in hr_zones)
    zone_percentages = {}

    if total_time > 0:
        for zone in hr_zones:
            zone_num = zone.get("zoneNumber")
            secs_in_zone = zone.get("secsInZone", 0)

            if zone_num:
                percentage = (secs_in_zone / total_time) * 100
                zone_percentages[f"zone{zone_num}_percentage"] = round(percentage, 2)

    # Determine training type
    # Primary: Use Garmin's trainingEffectLabel
    training_type = None
    if training_effect_label:
        # Convert to lowercase (e.g., "AEROBIC_BASE" → "aerobic_base")
        training_type = training_effect_label.lower()

    # Fallback: HR threshold-based classification
    if not training_type:
        avg_hr = summary_dto.get("averageHR", 0)

        # Extract zone boundaries from hr_zones list
        zone_boundaries = {}
        for zone in hr_zones:
            zone_num = zone.get("zoneNumber")
            if zone_num:
                zone_boundaries[zone_num] = zone.get("zoneLowBoundary", 0)

        # Default thresholds if zones not available
        z1_high = zone_boundaries.get(2, 120)
        z2_high = zone_boundaries.get(3, 140)
        z3_high = zone_boundaries.get(4, 160)

        if avg_hr <= z1_high:
            training_type = "aerobic_base"
        elif avg_hr <= z2_high:
            training_type = "tempo_run"
        elif avg_hr <= z3_high:
            training_type = "threshold_work"
        else:
            training_type = "mixed_effort"

    # Calculate HR stability (simplified, would need time series data for accurate calculation)
    # For now, use a simplified heuristic based on max-min HR range
    avg_hr = summary_dto.get("averageHR", 0)
    max_hr = summary_dto.get("maxHR", 0)
    min_hr = summary_dto.get("minHR", 0)

    hr_range = max_hr - min_hr
    # Simple heuristic: if HR range is small relative to average, it's stable
    hr_stability = "優秀" if avg_hr > 0 and (hr_range / avg_hr) < 0.3 else "変動あり"

    return {
        "hr_stability": hr_stability,
        "training_type": training_type,
        **zone_percentages,
    }


def insert_hr_efficiency(
    performance_file: str | None,
    activity_id: int,
    db_path: str | None = None,
    raw_hr_zones_file: str | None = None,
    raw_activity_file: str | None = None,
) -> bool:
    """
    Insert hr_efficiency_analysis from performance.json or raw data into DuckDB hr_efficiency table.

    Steps:
    1. Load performance.json (legacy) or raw data files (hr_zones.json + activity.json)
    2. Extract or calculate hr_efficiency_analysis
    3. Insert into hr_efficiency table (including zone percentages)

    Args:
        performance_file: Path to performance.json (legacy, optional)
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_hr_zones_file: Path to hr_zones.json (for raw mode)
        raw_activity_file: Path to activity.json (for raw mode)

    Returns:
        True if successful, False otherwise
    """
    try:
        use_raw_data = performance_file is None

        if use_raw_data:
            # Extract from raw data
            hr_eff = _extract_hr_efficiency_from_raw(
                raw_hr_zones_file, raw_activity_file
            )
            # Check if extraction failed (empty dict)
            if not hr_eff:
                logger.error("Failed to extract HR efficiency data from raw files")
                return False
        else:
            # Legacy: Load performance.json
            # Type narrowing for mypy
            assert performance_file is not None
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
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

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

        # Insert hr_efficiency data with zone percentages
        conn.execute(
            """
            INSERT INTO hr_efficiency (
                activity_id,
                hr_stability,
                training_type,
                zone1_percentage,
                zone2_percentage,
                zone3_percentage,
                zone4_percentage,
                zone5_percentage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                hr_eff.get("hr_stability"),
                hr_eff.get("training_type"),
                hr_eff.get("zone1_percentage"),
                hr_eff.get("zone2_percentage"),
                hr_eff.get("zone3_percentage"),
                hr_eff.get("zone4_percentage"),
                hr_eff.get("zone5_percentage"),
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
