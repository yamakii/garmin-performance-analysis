"""
PerformanceTrendsInserter - Insert performance_trends to DuckDB

Extracts phase-based performance analysis from raw splits.json and inserts into
performance_trends table. Supports both 4-phase (warmup/run/recovery/cooldown)
and legacy 3-phase (warmup/main/finish) structures.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def _map_intensity_to_phase(intensity_type: str | None) -> str | None:
    """Map Garmin intensityType to role_phase."""
    if not intensity_type:
        return None

    intensity_upper = intensity_type.upper()

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


def _extract_performance_trends_from_raw(raw_splits_file: str) -> dict | None:
    """
    Extract performance trends from raw splits.json.

    Analyzes splits by intensityType to detect phases (warmup/run/recovery/cooldown)
    and calculates phase-level statistics.

    Args:
        raw_splits_file: Path to splits.json

    Returns:
        Dictionary with performance_trends matching performance.json structure
    """
    import statistics

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

    # Group splits by phase
    warmup_splits = []
    run_splits = []
    recovery_splits = []
    cooldown_splits = []

    for lap in lap_dtos:
        lap_index = lap.get("lapIndex")
        if lap_index is None:
            continue

        intensity_type = lap.get("intensityType")
        phase = _map_intensity_to_phase(intensity_type)

        distance_m = lap.get("distance", 0)
        distance_km = distance_m / 1000.0 if distance_m else None
        duration = lap.get("duration")

        # Calculate pace (seconds per km)
        if distance_km and distance_km > 0 and duration:
            pace = duration / distance_km
        else:
            pace = None

        hr = lap.get("averageHR")
        cadence = lap.get("averageRunCadence")
        power = lap.get("averagePower")

        lap_data = {
            "lap_index": lap_index,
            "pace": pace,
            "hr": hr,
            "cadence": cadence,
            "power": power,
        }

        if phase == "warmup":
            warmup_splits.append(lap_data)
        elif phase == "run":
            run_splits.append(lap_data)
        elif phase == "recovery":
            recovery_splits.append(lap_data)
        elif phase == "cooldown":
            cooldown_splits.append(lap_data)

    # Calculate phase statistics
    def calc_phase_stats(splits):
        if not splits:
            return None

        lap_indices = [s["lap_index"] for s in splits]
        paces = [s["pace"] for s in splits if s["pace"] is not None]
        hrs = [s["hr"] for s in splits if s["hr"] is not None]
        cadences = [s["cadence"] for s in splits if s["cadence"] is not None]
        powers = [s["power"] for s in splits if s["power"] is not None]

        return {
            "splits": lap_indices,
            "avg_pace": statistics.mean(paces) if paces else None,
            "avg_hr": statistics.mean(hrs) if hrs else None,
            "avg_cadence": statistics.mean(cadences) if cadences else None,
            "avg_power": statistics.mean(powers) if powers else None,
        }

    result = {}

    # Calculate phase stats
    warmup_stats = calc_phase_stats(warmup_splits)
    if warmup_stats:
        result["warmup_phase"] = warmup_stats

    run_stats = calc_phase_stats(run_splits)
    if run_stats:
        result["run_phase"] = run_stats

    recovery_stats = calc_phase_stats(recovery_splits)
    if recovery_stats:
        result["recovery_phase"] = recovery_stats

    cooldown_stats = calc_phase_stats(cooldown_splits)
    if cooldown_stats:
        result["cooldown_phase"] = cooldown_stats

    # Calculate pace consistency (if we have run phase)
    if run_stats and run_splits:
        run_paces = [s["pace"] for s in run_splits if s["pace"] is not None]
        if len(run_paces) > 1:
            pace_std = statistics.stdev(run_paces)
            pace_mean = statistics.mean(run_paces)
            result["pace_consistency"] = pace_std / pace_mean if pace_mean > 0 else None
        else:
            result["pace_consistency"] = 0.0

    # Calculate HR drift (warmup to run or run to cooldown)
    if warmup_stats and run_stats:
        warmup_hr = warmup_stats.get("avg_hr")
        run_hr = run_stats.get("avg_hr")
        if warmup_hr and run_hr and warmup_hr > 0:
            result["hr_drift_percentage"] = ((run_hr - warmup_hr) / warmup_hr) * 100
    elif run_stats and cooldown_stats:
        run_hr = run_stats.get("avg_hr")
        cooldown_hr = cooldown_stats.get("avg_hr")
        if run_hr and cooldown_hr and run_hr > 0:
            result["hr_drift_percentage"] = ((cooldown_hr - run_hr) / run_hr) * 100

    # Calculate phase evaluations
    # 1. Warmup evaluation
    if warmup_stats:
        warmup_hr = warmup_stats.get("avg_hr")
        warmup_pace = warmup_stats.get("avg_pace")

        if warmup_hr and warmup_pace:
            # Good warmup: gradual start, HR in zone 1-2
            if warmup_hr < 140:  # Zone 1-2
                result["warmup_evaluation"] = "Good warmup"
            elif warmup_hr < 150:
                result["warmup_evaluation"] = "Minimal warmup"
            else:
                result["warmup_evaluation"] = "Minimal warmup"
        else:
            result["warmup_evaluation"] = "Minimal warmup"
    else:
        result["warmup_evaluation"] = "No warmup"

    # 2. Run evaluation
    if run_stats:
        run_hr = run_stats.get("avg_hr")
        run_pace = run_stats.get("avg_pace")

        if run_hr and run_pace:
            # Good run: steady pace and appropriate HR for effort
            pace_consistency_val = result.get("pace_consistency", 0)
            if pace_consistency_val is not None and pace_consistency_val < 0.05:
                # Very consistent pace
                if run_hr >= 145:  # Zone 3+
                    result["run_evaluation"] = "Excellent"
                else:
                    result["run_evaluation"] = "Good"
            elif pace_consistency_val is not None and pace_consistency_val < 0.10:
                result["run_evaluation"] = "Good"
            else:
                result["run_evaluation"] = "Fair"
        else:
            result["run_evaluation"] = "Fair"
    else:
        result["run_evaluation"] = "Poor"

    # 3. Recovery evaluation
    if recovery_stats and run_stats:
        recovery_hr = recovery_stats.get("avg_hr")
        recovery_cadence = recovery_stats.get("avg_cadence")
        run_hr = run_stats.get("avg_hr")
        run_cadence = run_stats.get("avg_cadence")

        if recovery_hr and run_hr:
            hr_drop = run_hr - recovery_hr
            cadence_drop = 0
            if recovery_cadence and run_cadence:
                cadence_drop = run_cadence - recovery_cadence

            # Good recovery: HR drops significantly, cadence drops ≥10 spm
            if hr_drop >= 10 and cadence_drop >= 10:
                result["recovery_evaluation"] = "Excellent recovery"
            elif hr_drop >= 5:
                result["recovery_evaluation"] = "Good recovery"
            else:
                result["recovery_evaluation"] = "Insufficient recovery"
        else:
            result["recovery_evaluation"] = "Insufficient recovery"
    elif not recovery_stats:
        result["recovery_evaluation"] = "No recovery"
    else:
        result["recovery_evaluation"] = "Insufficient recovery"

    # 4. Cooldown evaluation
    if cooldown_stats:
        cooldown_hr = cooldown_stats.get("avg_hr")
        cooldown_pace = cooldown_stats.get("avg_pace")

        if cooldown_hr and cooldown_pace:
            # Good cooldown: gradual decrease, HR in zone 1-2
            if cooldown_hr < 140:  # Zone 1-2
                result["cooldown_evaluation"] = "Good cooldown"
            elif cooldown_hr < 150:
                result["cooldown_evaluation"] = "Minimal cooldown"
            else:
                result["cooldown_evaluation"] = "Minimal cooldown"
        else:
            result["cooldown_evaluation"] = "Minimal cooldown"
    else:
        result["cooldown_evaluation"] = "No cooldown"

    # Simplified cadence consistency and fatigue pattern
    # (would require more sophisticated analysis in production)
    result["cadence_consistency"] = "安定"
    result["fatigue_pattern"] = "適切"

    return result


def insert_performance_trends(
    activity_id: int,
    db_path: str | None = None,
    raw_splits_file: str | None = None,
) -> bool:
    """
    Insert performance_trends from raw splits.json into DuckDB performance_trends table.

    Supports both:
    - New 4-phase structure: warmup/run/recovery/cooldown (interval training)
    - Legacy 3-phase structure: warmup/main/finish (regular runs)

    Steps:
    1. Load raw splits.json
    2. Extract and calculate performance_trends
    3. Detect phase structure (3-phase or 4-phase)
    4. Convert splits arrays to comma-separated strings
    5. Insert into performance_trends table

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_splits_file: Path to raw splits.json

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        if not raw_splits_file:
            logger.error("raw_splits_file required")
            return False

        perf_trends = _extract_performance_trends_from_raw(raw_splits_file)
        if not perf_trends:
            logger.error("Failed to extract performance trends from raw data")
            return False

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure performance_trends table exists with 4-phase schema
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_pace_str VARCHAR,
                warmup_avg_hr DOUBLE,
                warmup_avg_cadence DOUBLE,
                warmup_avg_power DOUBLE,
                warmup_evaluation VARCHAR,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_pace_str VARCHAR,
                run_avg_hr DOUBLE,
                run_avg_cadence DOUBLE,
                run_avg_power DOUBLE,
                run_evaluation VARCHAR,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_pace_str VARCHAR,
                recovery_avg_hr DOUBLE,
                recovery_avg_cadence DOUBLE,
                recovery_avg_power DOUBLE,
                recovery_evaluation VARCHAR,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_pace_str VARCHAR,
                cooldown_avg_hr DOUBLE,
                cooldown_avg_cadence DOUBLE,
                cooldown_avg_power DOUBLE,
                cooldown_evaluation VARCHAR
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM performance_trends WHERE activity_id = ?", [activity_id]
        )

        # Detect phase structure (4-phase or legacy 3-phase)
        has_run_phase = "run_phase" in perf_trends
        has_main_phase = "main_phase" in perf_trends

        # Helper function to format pace
        def format_pace(pace_seconds):
            if pace_seconds is None:
                return None
            minutes = int(pace_seconds // 60)
            seconds = int(pace_seconds % 60)
            return f"{minutes}:{seconds:02d}"

        if has_run_phase:
            # New 4-phase structure
            warmup_phase = perf_trends.get("warmup_phase", {})
            run_phase = perf_trends.get("run_phase", {})
            recovery_phase = perf_trends.get("recovery_phase", {})
            cooldown_phase = perf_trends.get("cooldown_phase", {})

            # Convert splits arrays to comma-separated strings
            warmup_splits = ",".join(str(s) for s in warmup_phase.get("splits", []))
            run_splits = ",".join(str(s) for s in run_phase.get("splits", []))
            recovery_splits = ",".join(str(s) for s in recovery_phase.get("splits", []))
            cooldown_splits = ",".join(str(s) for s in cooldown_phase.get("splits", []))

            # Insert with 4-phase data (including cadence, power, evaluation)
            conn.execute(
                """
                INSERT INTO performance_trends (
                    activity_id,
                    pace_consistency,
                    hr_drift_percentage,
                    cadence_consistency,
                    fatigue_pattern,
                    warmup_splits,
                    warmup_avg_pace_seconds_per_km,
                    warmup_avg_pace_str,
                    warmup_avg_hr,
                    warmup_avg_cadence,
                    warmup_avg_power,
                    warmup_evaluation,
                    run_splits,
                    run_avg_pace_seconds_per_km,
                    run_avg_pace_str,
                    run_avg_hr,
                    run_avg_cadence,
                    run_avg_power,
                    run_evaluation,
                    recovery_splits,
                    recovery_avg_pace_seconds_per_km,
                    recovery_avg_pace_str,
                    recovery_avg_hr,
                    recovery_avg_cadence,
                    recovery_avg_power,
                    recovery_evaluation,
                    cooldown_splits,
                    cooldown_avg_pace_seconds_per_km,
                    cooldown_avg_pace_str,
                    cooldown_avg_hr,
                    cooldown_avg_cadence,
                    cooldown_avg_power,
                    cooldown_evaluation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    perf_trends.get("pace_consistency"),
                    perf_trends.get("hr_drift_percentage"),
                    perf_trends.get("cadence_consistency"),
                    perf_trends.get("fatigue_pattern"),
                    warmup_splits,
                    warmup_phase.get("avg_pace"),
                    format_pace(warmup_phase.get("avg_pace")),
                    warmup_phase.get("avg_hr"),
                    warmup_phase.get("avg_cadence"),
                    warmup_phase.get("avg_power"),
                    perf_trends.get("warmup_evaluation"),
                    run_splits,
                    run_phase.get("avg_pace"),
                    format_pace(run_phase.get("avg_pace")),
                    run_phase.get("avg_hr"),
                    run_phase.get("avg_cadence"),
                    run_phase.get("avg_power"),
                    perf_trends.get("run_evaluation"),
                    recovery_splits,
                    recovery_phase.get("avg_pace"),
                    format_pace(recovery_phase.get("avg_pace")),
                    recovery_phase.get("avg_hr"),
                    recovery_phase.get("avg_cadence"),
                    recovery_phase.get("avg_power"),
                    perf_trends.get("recovery_evaluation"),
                    cooldown_splits,
                    cooldown_phase.get("avg_pace"),
                    format_pace(cooldown_phase.get("avg_pace")),
                    cooldown_phase.get("avg_hr"),
                    cooldown_phase.get("avg_cadence"),
                    cooldown_phase.get("avg_power"),
                    perf_trends.get("cooldown_evaluation"),
                ],
            )
            logger.info(
                f"Inserted 4-phase performance trends for activity {activity_id}"
            )

        elif has_main_phase:
            # Legacy 3-phase structure - insert into warmup/run/cooldown columns
            # (main → run, finish → cooldown)
            warmup_phase = perf_trends.get("warmup_phase", {})
            main_phase = perf_trends.get("main_phase", {})
            finish_phase = perf_trends.get("finish_phase", {})

            # Convert splits arrays to comma-separated strings
            warmup_splits = ",".join(str(s) for s in warmup_phase.get("splits", []))
            run_splits = ",".join(str(s) for s in main_phase.get("splits", []))
            cooldown_splits = ",".join(str(s) for s in finish_phase.get("splits", []))

            # Insert legacy 3-phase data (map to 4-phase columns)
            conn.execute(
                """
                INSERT INTO performance_trends (
                    activity_id,
                    pace_consistency,
                    hr_drift_percentage,
                    cadence_consistency,
                    fatigue_pattern,
                    warmup_splits,
                    warmup_avg_pace_seconds_per_km,
                    warmup_avg_pace_str,
                    warmup_avg_hr,
                    run_splits,
                    run_avg_pace_seconds_per_km,
                    run_avg_pace_str,
                    run_avg_hr,
                    cooldown_splits,
                    cooldown_avg_pace_seconds_per_km,
                    cooldown_avg_pace_str,
                    cooldown_avg_hr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    perf_trends.get("pace_consistency"),
                    perf_trends.get("hr_drift_percentage"),
                    perf_trends.get("cadence_consistency"),
                    perf_trends.get("fatigue_pattern"),
                    warmup_splits,
                    warmup_phase.get("avg_pace"),
                    format_pace(warmup_phase.get("avg_pace")),
                    warmup_phase.get("avg_hr"),
                    run_splits,
                    main_phase.get("avg_pace"),
                    format_pace(main_phase.get("avg_pace")),
                    main_phase.get("avg_hr"),
                    cooldown_splits,
                    finish_phase.get("avg_pace"),
                    format_pace(finish_phase.get("avg_pace")),
                    finish_phase.get("avg_hr"),
                ],
            )
            logger.info(
                f"Inserted legacy 3-phase performance trends for activity {activity_id}"
            )

        else:
            logger.error("Unknown phase structure in performance_trends")
            conn.close()
            return False

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Error inserting performance trends: {e}")
        return False
