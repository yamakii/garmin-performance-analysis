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

# raw Garmin/fallback training-type label → canonical intensity category.
# Each canonical category is scored against its own correct HR-zone band so that
# easy runs are rewarded for staying low (Zone1-2) instead of being penalised for
# not spending time in high zones.
_CANONICAL_CATEGORY_LABELS: dict[str, frozenset[str]] = {
    "easy": frozenset(
        {"aerobic_base", "recovery", "low_moderate", "base", "warmup", "easy"}
    ),
    "tempo": frozenset({"tempo", "tempo_run"}),
    "threshold": frozenset({"lactate_threshold", "threshold_work", "threshold"}),
    "vo2max": frozenset(
        {
            "vo2max",
            "vo2_max",
            "anaerobic_capacity",
            "anaerobic",
            "interval_sprint",
            "speed",
            "sprint",
        }
    ),
}


def _canonical_training_category(training_type: str | None) -> str:
    """raw Garmin/fallback ラベル → 正準強度カテゴリ。

    returns: "easy" | "tempo" | "threshold" | "vo2max" | "unknown"

    "unknown" (unknown/mixed_effort/None など未知ラベル) は減点しない中立扱い。
    """
    if not training_type:
        return "unknown"

    normalized = training_type.lower()
    for category, labels in _CANONICAL_CATEGORY_LABELS.items():
        if normalized in labels:
            return category
    return "unknown"


# A Zone3-dominant run with negligible Zone4-5 is a controlled MODERATE aerobic
# effort, not a failed easy run. The label alone (e.g. "aerobic_base") cannot tell
# these apart, so refine the label-category with the actual zone distribution.
_MODERATE_ZONE3_MIN = 50.0  # Zone3 % that marks a run as Zone3-dominant
_MODERATE_ZONE45_MAX = 15.0  # Zone4+5 % below which it is not threshold/VO2 work
# Zone4+5 % above which the session actually did threshold work. Also the
# alignment evidence for a quality session whose modal zone is the warmup's
# (Issue #1086).
_THRESHOLD_WORK_MIN_PCT = 20.0


def resolve_intensity_category(
    training_type: str | None,
    zone1_pct: float,
    zone2_pct: float,
    zone3_pct: float,
    zone4_pct: float,
    zone5_pct: float,
    primary_zone: str | None,
) -> str:
    """label-category を base に、実ゾーン分布で強度カテゴリを解決する。

    returns: "easy" | "moderate" | "tempo" | "threshold" | "vo2max" | "unknown"

    easy/unknown 系ラベルでも Zone3 優勢（primary=Zone3 かつ zone3 >= 50%）で
    Zone4+5 < 15%（閾値/無酸素練でない）なら "moderate" に refine する。
    これにより制御された中強度走が easy(Zone1-2)基準で不当に Poor になるのを防ぐ。
    tempo/threshold/vo2max ラベルは意図が明確なので refine しない。
    """
    base = _canonical_training_category(training_type)
    if base in ("easy", "unknown"):
        zone45_pct = zone4_pct + zone5_pct
        if (
            primary_zone == "Zone 3"
            and zone3_pct >= _MODERATE_ZONE3_MIN
            and zone45_pct < _MODERATE_ZONE45_MAX
        ):
            return "moderate"
    return base


# (excellent_cut, good_cut, fair_cut) per canonical intensity category, as a
# percentage of the run spent in the band that category is judged on (see
# ``zone_band_pct``). Single source of truth: the categorical label, the
# continuous ``zone_distribution_score`` and the analysis contracts' zone
# targets all read these numbers, so a target stated to the agent can never
# drift away from the cut that actually decides the rating (#1235).
ZONE_BAND_CUTS: dict[str, tuple[float, float, float]] = {
    "easy": (90.0, 75.0, 60.0),
    "moderate": (80.0, 60.0, 40.0),
    "tempo": (60.0, 40.0, 20.0),
    "threshold": (60.0, 40.0, 20.0),
    "vo2max": (50.0, 30.0, 15.0),
}

# "unknown" has no intended band, so it is judged loosely on the whole aerobic
# range and never drops below "Fair".
_UNKNOWN_GOOD_CUT = 70.0

_SCORE_FLOOR = 1.0
_SCORE_CEILING = 5.0


def zone_band_pct(
    category: str,
    zone1_pct: float,
    zone2_pct: float,
    zone3_pct: float,
    zone4_pct: float,
    zone5_pct: float,
) -> float:
    """The % of the run in the HR-zone band the category is judged on.

    easy -> Zone1-2, moderate -> Zone2-3, tempo/threshold -> Zone3-4,
    vo2max -> Zone4-5, unknown -> Zone1-3 (loose aerobic range).
    """
    if category == "easy":
        return zone1_pct + zone2_pct
    if category == "moderate":
        return zone2_pct + zone3_pct
    if category in ("tempo", "threshold"):
        return zone3_pct + zone4_pct
    if category == "vo2max":
        return zone4_pct + zone5_pct
    return zone1_pct + zone2_pct + zone3_pct


def zone_distribution_rating(category: str, band_pct: float) -> str:
    """Categorical zone-distribution label, read from ``ZONE_BAND_CUTS``.

    returns: "Excellent" | "Good" | "Fair" | "Poor"
    """
    cuts = ZONE_BAND_CUTS.get(category)
    if cuts is None:
        # unknown: neutral, never penalised down to Poor.
        return "Good" if band_pct >= _UNKNOWN_GOOD_CUT else "Fair"

    excellent_cut, good_cut, fair_cut = cuts
    if band_pct >= excellent_cut:
        return "Excellent"
    if band_pct >= good_cut:
        return "Good"
    if band_pct >= fair_cut:
        return "Fair"
    return "Poor"


def zone_distribution_score(category: str, band_pct: float) -> float | None:
    """Continuous 1.0-5.0 zone-distribution score over ``ZONE_BAND_CUTS``.

    The label is categorical, so a run one point below a cut lost a whole
    quality step and the LLM-scored hr_management axis jumped about a full star
    at the edge (#1235). This interpolates linearly between the same cuts:
    excellent cut -> 5.0, good cut -> 4.0, fair cut -> 3.0, and below the fair
    cut it keeps the good->fair slope down to a floor of 1.0. At or above the
    excellent cut the score is 5.0.

    Args:
        category: canonical intensity category (``resolve_intensity_category``).
        band_pct: % of the run in that category's band (``zone_band_pct``).

    Returns:
        Score in 1.0-5.0 with one decimal, or None for "unknown", which carries
        no intended band and is never penalised today.
    """
    cuts = ZONE_BAND_CUTS.get(category)
    if cuts is None:
        return None

    excellent_cut, good_cut, fair_cut = cuts
    if band_pct >= excellent_cut:
        score = _SCORE_CEILING
    elif band_pct >= good_cut:
        score = 4.0 + (band_pct - good_cut) / (excellent_cut - good_cut)
    else:
        # The same good->fair slope continues below the fair cut, so the curve
        # stays straight through "Fair" into "Poor" instead of stepping again.
        score = 3.0 + (band_pct - fair_cut) / (good_cut - fair_cut)

    return round(max(_SCORE_FLOOR, min(_SCORE_CEILING, score)), 1)


# Quality ladder, lowest to highest. A rating step is worth one quality step and
# being misaligned with the intended primary zone costs exactly one more step.
_QUALITY_LADDER = ("Poor", "Fair", "Good", "Excellent")


def _combine_training_quality(rating: str, aligned: bool) -> str:
    """Combine zone_distribution_rating with primary-zone alignment.

    Excellent + aligned            -> "Excellent"
    Excellent (misaligned)         -> "Good"
    Good + aligned                 -> "Good"
    Good (misaligned)              -> "Fair"
    Fair + aligned                 -> "Fair"
    Fair (misaligned), Poor        -> "Poor"

    A "Fair" rating used to collapse to "Poor" whatever the alignment, so an
    aligned easy run one step below Good lost two quality steps at once
    (Issue #1232). Demoting by a single step keeps the ladder proportional.
    """
    if rating not in _QUALITY_LADDER:
        # Unknown rating: stay neutral instead of punishing the session.
        return "Fair"

    index = _QUALITY_LADDER.index(rating)
    if not aligned:
        index -= 1
    return _QUALITY_LADDER[max(index, 0)]


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

    # 2. Calculate zone_distribution_rating based on the canonical intensity
    #    category, scoring each category against its own correct HR-zone band.
    zone1_pct = zone_percentages.get("zone1_percentage", 0)
    zone2_pct = zone_percentages.get("zone2_percentage", 0)
    zone3_pct = zone_percentages.get("zone3_percentage", 0)
    zone4_pct = zone_percentages.get("zone4_percentage", 0)
    zone5_pct = zone_percentages.get("zone5_percentage", 0)

    # Resolve the intensity category from the label refined by the actual zone
    # distribution (Zone3-dominant controlled runs become "moderate").
    category = resolve_intensity_category(
        training_type,
        zone1_pct,
        zone2_pct,
        zone3_pct,
        zone4_pct,
        zone5_pct,
        primary_zone,
    )

    # Each category is judged on its own band (easy Zone1-2, moderate Zone2-3,
    # tempo/threshold Zone3-4, vo2max Zone4-5) against ZONE_BAND_CUTS.
    band_pct = zone_band_pct(
        category, zone1_pct, zone2_pct, zone3_pct, zone4_pct, zone5_pct
    )
    rating = zone_distribution_rating(category, band_pct)

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
    # Check if primary zone aligns with the canonical intensity category.
    # easy → Zone1/Zone2, tempo/threshold → Zone3/Zone4, vo2max → Zone4/Zone5,
    # unknown → always aligned (neutral).
    primary_zone_aligned = False
    if category == "unknown":
        primary_zone_aligned = True
    elif primary_zone:
        if category == "easy":
            primary_zone_aligned = "Zone 1" in primary_zone or "Zone 2" in primary_zone
        elif category == "moderate":
            primary_zone_aligned = "Zone 2" in primary_zone or "Zone 3" in primary_zone
        elif category in ("tempo", "threshold"):
            # A quality session carries the warmup / cooldown its prescription
            # registers (10min + 5min) and a build-up opens in Zone2, so the
            # modal zone is routinely Zone1-2 even when the threshold work was
            # done exactly as prescribed. Spending real time at Zone4-5 is the
            # evidence that the session met its intent, so it counts as
            # alignment on its own (Issue #1086).
            primary_zone_aligned = (
                "Zone 3" in primary_zone
                or "Zone 4" in primary_zone
                or (zone4_pct + zone5_pct) > _THRESHOLD_WORK_MIN_PCT
            )
        elif category == "vo2max":
            primary_zone_aligned = "Zone 4" in primary_zone or "Zone 5" in primary_zone

    # Combine rating with alignment
    training_quality = _combine_training_quality(rating, primary_zone_aligned)

    # 5. Calculate zone2_focus (Zone 2 time > 60%)
    zone2_focus = zone2_pct > 60

    # 6. Calculate zone4_threshold_work (Zone 4-5 time > 20%)
    zone4_pct = zone_percentages.get("zone4_percentage", 0)
    zone5_pct = zone_percentages.get("zone5_percentage", 0)
    zone45_pct = zone4_pct + zone5_pct
    zone4_threshold_work = zone45_pct > _THRESHOLD_WORK_MIN_PCT

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
        "zone_distribution_rating": rating,
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
