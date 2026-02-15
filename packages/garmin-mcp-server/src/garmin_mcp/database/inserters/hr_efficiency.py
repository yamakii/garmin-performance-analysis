"""
HREfficiencyInserter - Insert hr_efficiency_analysis to DuckDB

Inserts heart rate efficiency analysis from raw data (hr_zones.json + activity.json)
into hr_efficiency table.
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

    # Calculate zone times and percentages
    total_time = sum(zone.get("secsInZone", 0) for zone in hr_zones)
    zone_times = {}
    zone_percentages = {}

    if total_time > 0:
        for zone in hr_zones:
            zone_num = zone.get("zoneNumber")
            secs_in_zone = zone.get("secsInZone", 0)

            if zone_num:
                zone_times[zone_num] = secs_in_zone
                percentage = (secs_in_zone / total_time) * 100
                zone_percentages[f"zone{zone_num}_percentage"] = round(percentage, 2)

    # 1. Calculate primary_zone (zone with highest time)
    primary_zone = None
    if zone_times:
        max_zone_num = max(zone_times.keys(), key=lambda z: zone_times[z])
        primary_zone = f"Zone {max_zone_num}"

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

    # 2. Calculate zone_distribution_rating based on training_type
    zone_distribution_rating = "Fair"  # default

    if training_type:
        zone2_pct = zone_percentages.get("zone2_percentage", 0)
        zone3_pct = zone_percentages.get("zone3_percentage", 0)
        zone4_pct = zone_percentages.get("zone4_percentage", 0)
        zone5_pct = zone_percentages.get("zone5_percentage", 0)

        if training_type in ("recovery", "low_moderate"):
            # Zone 2 ≥70% → Excellent, ≥50% → Good
            if zone2_pct >= 70:
                zone_distribution_rating = "Excellent"
            elif zone2_pct >= 50:
                zone_distribution_rating = "Good"
            elif zone2_pct >= 30:
                zone_distribution_rating = "Fair"
            else:
                zone_distribution_rating = "Poor"
        elif training_type in ("tempo_run", "threshold_work"):
            # Zone 3-4 ≥60% → Excellent, ≥40% → Good
            zone34_pct = zone3_pct + zone4_pct
            if zone34_pct >= 60:
                zone_distribution_rating = "Excellent"
            elif zone34_pct >= 40:
                zone_distribution_rating = "Good"
            elif zone34_pct >= 20:
                zone_distribution_rating = "Fair"
            else:
                zone_distribution_rating = "Poor"
        elif training_type in ("interval_sprint", "vo2_max"):
            # Zone 4-5 ≥50% → Excellent, ≥30% → Good
            zone45_pct = zone4_pct + zone5_pct
            if zone45_pct >= 50:
                zone_distribution_rating = "Excellent"
            elif zone45_pct >= 30:
                zone_distribution_rating = "Good"
            elif zone45_pct >= 15:
                zone_distribution_rating = "Fair"
            else:
                zone_distribution_rating = "Poor"
        else:
            # aerobic_base or other types - default to Zone 2-3 focus
            zone23_pct = zone2_pct + zone3_pct
            if zone23_pct >= 70:
                zone_distribution_rating = "Excellent"
            elif zone23_pct >= 50:
                zone_distribution_rating = "Good"
            elif zone23_pct >= 30:
                zone_distribution_rating = "Fair"
            else:
                zone_distribution_rating = "Poor"

    # 3. Calculate aerobic_efficiency (Zone 2-3 percentage)
    zone2_pct = zone_percentages.get("zone2_percentage", 0)
    zone3_pct = zone_percentages.get("zone3_percentage", 0)
    aerobic_pct = zone2_pct + zone3_pct

    if aerobic_pct >= 80:
        aerobic_efficiency = "Excellent aerobic base"
    elif aerobic_pct >= 60:
        aerobic_efficiency = "Good aerobic development"
    elif aerobic_pct >= 40:
        aerobic_efficiency = "Moderate aerobic work"
    else:
        aerobic_efficiency = "Limited aerobic stimulus"

    # 4. Calculate training_quality (combine zone_distribution_rating + primary_zone alignment)
    training_quality = "Fair"  # default

    # Check if primary zone aligns with training type
    primary_zone_aligned = False
    if primary_zone and training_type:  # noqa: SIM102
        if (
            training_type in ("recovery", "low_moderate")
            and "Zone 2" in primary_zone
            or training_type in ("tempo_run", "threshold_work")
            and ("Zone 3" in primary_zone or "Zone 4" in primary_zone)
            or training_type in ("interval_sprint", "vo2_max")
            and ("Zone 4" in primary_zone or "Zone 5" in primary_zone)
            or training_type in ("aerobic_base",)
            and ("Zone 2" in primary_zone or "Zone 3" in primary_zone)
        ):
            primary_zone_aligned = True

    # Combine rating with alignment
    if zone_distribution_rating == "Excellent" and primary_zone_aligned:
        training_quality = "Excellent"
    elif zone_distribution_rating == "Excellent" or (
        zone_distribution_rating == "Good" and primary_zone_aligned
    ):
        training_quality = "Good"
    elif zone_distribution_rating == "Good":
        training_quality = "Fair"
    else:
        training_quality = "Poor"

    # 5. Calculate zone2_focus (Zone 2 time > 60%)
    zone2_focus = zone2_pct > 60

    # 6. Calculate zone4_threshold_work (Zone 4-5 time > 20%)
    zone4_pct = zone_percentages.get("zone4_percentage", 0)
    zone5_pct = zone_percentages.get("zone5_percentage", 0)
    zone45_pct = zone4_pct + zone5_pct
    zone4_threshold_work = zone45_pct > 20

    # Calculate HR stability (simplified)
    avg_hr = summary_dto.get("averageHR", 0)
    max_hr = summary_dto.get("maxHR", 0)
    min_hr = summary_dto.get("minHR", 0)

    hr_range = max_hr - min_hr
    # Simple heuristic: if HR range is small relative to average, it's stable
    hr_stability = "優秀" if avg_hr > 0 and (hr_range / avg_hr) < 0.3 else "変動あり"

    return {
        "hr_stability": hr_stability,
        "training_type": training_type,
        "primary_zone": primary_zone,
        "zone_distribution_rating": zone_distribution_rating,
        "aerobic_efficiency": aerobic_efficiency,
        "training_quality": training_quality,
        "zone2_focus": zone2_focus,
        "zone4_threshold_work": zone4_threshold_work,
        **zone_percentages,
    }


def insert_hr_efficiency(
    activity_id: int,
    conn: duckdb.DuckDBPyConnection,
    raw_hr_zones_file: str | None = None,
    raw_activity_file: str | None = None,
) -> bool:
    """
    Insert hr_efficiency_analysis from raw data into DuckDB hr_efficiency table.

    Extracts HR efficiency data from raw hr_zones.json and activity.json files
    and inserts into hr_efficiency table (including zone percentages).

    Args:
        activity_id: Activity ID
        conn: DuckDB connection
        raw_hr_zones_file: Path to hr_zones.json
        raw_activity_file: Path to activity.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        hr_eff = _extract_hr_efficiency_from_raw(raw_hr_zones_file, raw_activity_file)
        # Check if extraction failed (empty dict)
        if not hr_eff:
            logger.error("Failed to extract HR efficiency data from raw files")
            return False

        # Delete existing record for this activity (for re-insertion)
        conn.execute("DELETE FROM hr_efficiency WHERE activity_id = ?", [activity_id])

        # Insert hr_efficiency data with all new calculated fields
        conn.execute(
            """
            INSERT INTO hr_efficiency (
                activity_id,
                primary_zone,
                zone_distribution_rating,
                hr_stability,
                aerobic_efficiency,
                training_quality,
                zone2_focus,
                zone4_threshold_work,
                training_type,
                zone1_percentage,
                zone2_percentage,
                zone3_percentage,
                zone4_percentage,
                zone5_percentage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                hr_eff.get("primary_zone"),
                hr_eff.get("zone_distribution_rating"),
                hr_eff.get("hr_stability"),
                hr_eff.get("aerobic_efficiency"),
                hr_eff.get("training_quality"),
                hr_eff.get("zone2_focus"),
                hr_eff.get("zone4_threshold_work"),
                hr_eff.get("training_type"),
                hr_eff.get("zone1_percentage"),
                hr_eff.get("zone2_percentage"),
                hr_eff.get("zone3_percentage"),
                hr_eff.get("zone4_percentage"),
                hr_eff.get("zone5_percentage"),
            ],
        )

        logger.info(
            f"Successfully inserted HR efficiency data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting HR efficiency: {e}")
        return False
