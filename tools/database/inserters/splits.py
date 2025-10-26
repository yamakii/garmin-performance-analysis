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


def _calculate_hr_zone(heart_rate: float | None, hr_zones: list[dict]) -> str | None:
    """
    Map heart_rate to zone name using zone boundaries.

    Args:
        heart_rate: Heart rate in bpm
        hr_zones: List of zone dicts with zone_number, lower_bpm, upper_bpm

    Returns:
        Zone name (e.g., "Zone 2") or None

    Examples:
        >>> zones = [{"zone_number": 1, "lower_bpm": 100, "upper_bpm": 120},
        ...          {"zone_number": 2, "lower_bpm": 120, "upper_bpm": 150}]
        >>> _calculate_hr_zone(110, zones)
        'Zone 1'
        >>> _calculate_hr_zone(145, zones)
        'Zone 2'
    """
    if heart_rate is None:
        return None

    if not hr_zones:
        return None

    # Find matching zone
    for zone in hr_zones:
        zone_num = zone.get("zone_number")
        lower = zone.get("lower_bpm")
        upper = zone.get("upper_bpm")

        if lower is None or upper is None:
            continue

        if lower <= heart_rate <= upper:
            return f"Zone {zone_num}"

    # Fallback for values outside all zones
    first_zone_lower = hr_zones[0].get("lower_bpm")
    last_zone_upper = hr_zones[-1].get("upper_bpm")

    if first_zone_lower and heart_rate < first_zone_lower:
        return "Zone 0 (Recovery)"
    elif last_zone_upper and heart_rate > last_zone_upper:
        return "Zone 5+ (Max)"

    return None


def _calculate_cadence_rating(cadence: float | None) -> str | None:
    """
    Evaluate cadence quality based on running science.

    Thresholds:
    - <170: Low (target 180+)
    - 170-180: Good
    - 180-190: Excellent
    - 190+: Elite

    Args:
        cadence: Cadence in steps per minute (spm)

    Returns:
        Cadence rating string or None

    Examples:
        >>> _calculate_cadence_rating(175)
        'Good (175 spm)'
        >>> _calculate_cadence_rating(185)
        'Excellent (185 spm)'
    """
    if cadence is None:
        return None

    cadence_int = int(cadence)

    if cadence < 170:
        return f"Low ({cadence_int} spm, target 180+)"
    elif 170 <= cadence < 180:
        return f"Good ({cadence_int} spm)"
    elif 180 <= cadence < 190:
        return f"Excellent ({cadence_int} spm)"
    else:  # 190+
        return f"Elite ({cadence_int} spm)"


def _calculate_power_efficiency(
    power: float | None, weight_kg: float | None
) -> str | None:
    """
    Calculate power-to-weight ratio (W/kg).

    Args:
        power: Power in watts
        weight_kg: Body weight in kg

    Returns:
        Power efficiency rating or None

    Examples:
        >>> _calculate_power_efficiency(250, 70)
        'Moderate (3.6 W/kg)'
    """
    if power is None or weight_kg is None:
        return None

    w_per_kg = power / weight_kg

    if w_per_kg < 2.5:
        return f"Low ({w_per_kg:.1f} W/kg)"
    elif 2.5 <= w_per_kg < 3.5:
        return f"Moderate ({w_per_kg:.1f} W/kg)"
    elif 3.5 <= w_per_kg < 4.5:
        return f"Good ({w_per_kg:.1f} W/kg)"
    else:  # 4.5+
        return f"Excellent ({w_per_kg:.1f} W/kg)"


def _calculate_environmental_conditions(
    temp: float | None, wind: float | None, humidity: float | None
) -> str | None:
    """
    Summarize environmental conditions.

    Args:
        temp: Temperature in Celsius
        wind: Wind speed in km/h
        humidity: Humidity percentage

    Returns:
        Environmental conditions summary or None

    Examples:
        >>> _calculate_environmental_conditions(15, 2, 65)
        'Cool (15°C), Calm'
    """
    if temp is None:
        return None

    parts = []

    # Temperature descriptor
    if temp < 10:
        parts.append(f"Cold ({int(temp)}°C)")
    elif 10 <= temp < 18:
        parts.append(f"Cool ({int(temp)}°C)")
    elif 18 <= temp < 25:
        parts.append(f"Mild ({int(temp)}°C)")
    else:  # 25+
        parts.append(f"Hot ({int(temp)}°C)")

    # Wind descriptor (if available)
    if wind is not None:
        if wind < 5:
            parts.append("Calm")
        elif 5 <= wind < 15:
            parts.append(f"Breezy ({int(wind)} km/h)")
        else:  # 15+
            parts.append(f"Windy ({int(wind)} km/h)")

    # Humidity descriptor (if available)
    if humidity is not None:
        if humidity > 80:
            parts.append(f"Humid ({int(humidity)}%)")
        elif humidity < 30:
            parts.append(f"Dry ({int(humidity)}%)")

    return ", ".join(parts)


def _calculate_wind_impact(
    wind_speed: float | None, wind_dir: float | None = None
) -> str | None:
    """
    Evaluate wind impact on performance.

    Args:
        wind_speed: Wind speed in km/h
        wind_dir: Wind direction in degrees (0=N, 90=E, 180=S, 270=W)

    Returns:
        Wind impact evaluation or None

    Examples:
        >>> _calculate_wind_impact(3)
        'Minimal (<5 km/h)'
        >>> _calculate_wind_impact(12, 30)
        'Moderate headwind (12 km/h)'
    """
    if wind_speed is None:
        return None

    if wind_speed < 5:
        return "Minimal (<5 km/h)"
    elif 5 <= wind_speed < 15:
        # Enhance with direction if available
        if wind_dir is not None:
            # 0° = headwind, 90° = crosswind, 180° = tailwind
            if wind_dir < 45 or wind_dir > 315:
                return f"Moderate headwind ({int(wind_speed)} km/h)"
            elif 135 < wind_dir < 225:
                return f"Moderate tailwind ({int(wind_speed)} km/h)"
            else:
                return f"Moderate crosswind ({int(wind_speed)} km/h)"
        else:
            return f"Moderate ({int(wind_speed)} km/h)"
    else:  # 15+
        return f"Significant ({int(wind_speed)} km/h, pace impact expected)"


def _calculate_temp_impact(temp: float | None, training_type: str) -> str | None:
    """
    Evaluate temperature impact based on training intensity.

    Args:
        temp: Temperature in Celsius
        training_type: Training type (recovery, low_moderate, base, tempo_threshold, interval_sprint)

    Returns:
        Temperature impact evaluation or None

    Examples:
        >>> _calculate_temp_impact(15, "tempo_threshold")
        'Ideal (15°C)'
        >>> _calculate_temp_impact(28, "interval_sprint")
        'Too hot (28°C, consider rescheduling)'
    """
    if temp is None:
        return None

    temp_int = int(temp)

    # Ideal ranges vary by training intensity
    if training_type in ["recovery", "low_moderate"]:
        # Wider tolerance for low-intensity
        if 15 <= temp <= 22:
            return f"Good ({temp_int}°C)"
        elif 10 <= temp < 15 or 22 < temp <= 25:
            return f"Acceptable ({temp_int}°C)"
        elif temp < 10:
            return f"Cold ({temp_int}°C)"
        else:  # >25
            return f"Hot ({temp_int}°C)"

    elif training_type in ["base", "tempo_threshold"]:
        # Moderate tolerance
        if 10 <= temp <= 18:
            return f"Ideal ({temp_int}°C)"
        elif 18 < temp <= 23:
            return f"Acceptable ({temp_int}°C)"
        elif temp < 10:
            return f"Cool ({temp_int}°C)"
        else:  # >23
            return f"Hot ({temp_int}°C, hydration important)"

    else:  # interval_sprint
        # Narrow tolerance for high-intensity
        if 8 <= temp <= 15:
            return f"Ideal ({temp_int}°C)"
        elif 15 < temp <= 20:
            return f"Good ({temp_int}°C)"
        elif 20 < temp <= 25:
            return f"Warm ({temp_int}°C, performance may decrease)"
        elif temp < 8:
            return f"Cold ({temp_int}°C, longer warmup needed)"
        else:  # >25
            return f"Too hot ({temp_int}°C, consider rescheduling)"


def _calculate_environmental_impact(
    temp_impact: str | None,
    wind_impact: str | None,
    elevation_gain: float | None,
    elevation_loss: float | None,
) -> str:
    """
    Calculate overall environmental impact rating.

    Args:
        temp_impact: Temperature impact string
        wind_impact: Wind impact string
        elevation_gain: Elevation gain in meters
        elevation_loss: Elevation loss in meters

    Returns:
        Overall environmental impact rating

    Examples:
        >>> _calculate_environmental_impact("Ideal (15°C)", "Minimal (<5 km/h)", 3, 2)
        'Ideal conditions'
    """
    challenge_score = 0

    # Temperature challenge (0-3 points)
    if temp_impact:
        if "Too hot" in temp_impact or "Cold" in temp_impact:
            challenge_score += 3
        elif "Hot" in temp_impact or "Cool" in temp_impact:
            challenge_score += 2
        elif "Warm" in temp_impact:
            challenge_score += 1

    # Wind challenge (0-2 points)
    if wind_impact:
        if "Significant" in wind_impact:
            challenge_score += 2
        elif "Moderate" in wind_impact:
            challenge_score += 1

    # Terrain challenge (0-2 points)
    total_elevation = abs(elevation_gain or 0) + abs(elevation_loss or 0)
    if total_elevation > 100:  # Significant elevation change
        challenge_score += 2
    elif total_elevation > 50:
        challenge_score += 1

    # Rating based on total score (0-7 possible)
    if challenge_score == 0:
        return "Ideal conditions"
    elif challenge_score <= 2:
        return "Good conditions"
    elif challenge_score <= 4:
        return "Moderate challenge"
    elif challenge_score <= 5:
        return "Challenging conditions"
    else:  # 6-7
        return "Extreme conditions"


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


def _estimate_intensity_type(splits: list[dict]) -> list[str]:
    """
    Estimate intensity_type for splits based on HR and pace patterns.

    Algorithm (validated - 92.7% accuracy):
    - Calculate average HR and pace across all splits
    - For each split in order:
        1. WARMUP: First 2 splits (1 split if total ≤ 6)
        2. COOLDOWN: Last 2 splits (1 split if total ≤ 6)
        3. RECOVERY: pace > 400 sec/km AND previous split was INTERVAL/RECOVERY
        4. INTERVAL: pace < avg_pace * 0.90 OR hr > avg_hr * 1.1
        5. ACTIVE: Everything else (default)

    Args:
        splits: List of split dictionaries with 'avg_heart_rate' and 'pace_seconds_per_km' keys

    Returns:
        List of estimated intensity_type strings (same length as splits)

    Notes:
        - Validated accuracy: Threshold 88.9%, Sprint 93.8%, VO2 Max 95.5%
        - REST is mapped to RECOVERY (functionally equivalent)
        - Returns estimates only; does not modify input splits
        - Handles missing HR/pace values gracefully (use remaining non-null values for average)

    References:
        - Issue #40: https://github.com/yamakii/garmin-performance-analysis/issues/40
        - Planning: docs/project/2025-10-26_intensity_type_estimation/planning.md
    """
    total_splits = len(splits)

    # Handle empty input
    if total_splits == 0:
        return []

    # Handle single split - no warmup/cooldown designation
    if total_splits == 1:
        return ["ACTIVE"]

    # Calculate averages (skip splits with missing values)
    hrs: list[float] = [
        float(hr) for s in splits if (hr := s.get("avg_heart_rate")) is not None
    ]
    paces: list[float] = [
        float(pace)
        for s in splits
        if (pace := s.get("pace_seconds_per_km")) is not None
    ]

    avg_hr = sum(hrs) / len(hrs) if hrs else 0.0
    avg_pace = sum(paces) / len(paces) if paces else 0.0

    # If no data available, return all ACTIVE
    if avg_hr == 0 and avg_pace == 0:
        return ["ACTIVE"] * total_splits

    # Thresholds for warmup/cooldown (position-based)
    # For runs >6 splits: 2 warmup + 2 cooldown
    # For runs ≤6 splits: 1 warmup + 1 cooldown
    warmup_count = 2 if total_splits > 6 else 1
    cooldown_count = 2 if total_splits > 6 else 1

    estimated_types = []
    for idx, split in enumerate(splits):
        # Get split values (may be None)
        split_hr = split.get("avg_heart_rate")
        split_pace = split.get("pace_seconds_per_km")

        position = idx + 1  # 1-based position

        # Rule 1: WARMUP - first N splits (position-based)
        if position <= warmup_count:
            estimated_types.append("WARMUP")

        # Rule 2: COOLDOWN - last N splits (position-based)
        elif position > total_splits - cooldown_count:
            estimated_types.append("COOLDOWN")

        # Rule 3: RECOVERY - slow pace after INTERVAL/RECOVERY
        # Only check pace if it's not None
        elif (
            split_pace is not None
            and split_pace > 400
            and idx > 0
            and estimated_types[idx - 1] in ["INTERVAL", "RECOVERY"]
        ):
            estimated_types.append("RECOVERY")

        # Rule 4: INTERVAL - fast pace OR high HR
        # Check pace only if not None, check HR only if not None
        elif (split_pace is not None and split_pace < avg_pace * 0.90) or (
            split_hr is not None and split_hr > avg_hr * 1.1
        ):
            estimated_types.append("INTERVAL")

        # Rule 5: ACTIVE - everything else (default)
        else:
            estimated_types.append("ACTIVE")

    return estimated_types


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
