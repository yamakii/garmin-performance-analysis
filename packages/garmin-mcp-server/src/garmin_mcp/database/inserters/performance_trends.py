"""
PerformanceTrendsInserter - Insert performance_trends to DuckDB

Extracts phase-based performance analysis from raw splits.json and inserts into
performance_trends table. Supports 4-phase (warmup/run/recovery/cooldown) structure.
"""

import json
import logging
from pathlib import Path

import duckdb

from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper

logger = logging.getLogger(__name__)


def _compute_steady_decoupling(run_splits: list[dict]) -> float | None:
    """定常区間（run-phase lap群）の Pa:HR デカップリング%。

    run laps を前半/後半に二分し、各半分の効率比 (1/pace)/hr = 速度:HR を算出、
    decoupling% = (ratio_first - ratio_second) / ratio_first * 100 を返す。
    後半で同ペースなのにHRが上がる(効率低下)と正値。
    使用可能 lap が2本未満、または pace/hr 欠損で算出不能なら None。
    """
    import statistics

    valid = [
        s
        for s in run_splits
        if s.get("pace") is not None
        and s["pace"] > 0
        and s.get("hr") is not None
        and s["hr"] > 0
    ]
    if len(valid) < 2:
        return None

    mid = len(valid) // 2
    first_half = valid[:mid]
    second_half = valid[mid:]

    def efficiency_ratio(splits: list[dict]) -> float | None:
        if not splits:
            return None
        mean_pace = float(statistics.mean(float(s["pace"]) for s in splits))
        mean_hr = float(statistics.mean(float(s["hr"]) for s in splits))
        if mean_pace <= 0 or mean_hr <= 0:
            return None
        # speed:HR ratio = (1 / pace) / hr
        return (1.0 / mean_pace) / mean_hr

    ratio_first = efficiency_ratio(first_half)
    ratio_second = efficiency_ratio(second_half)
    if ratio_first is None or ratio_second is None or ratio_first == 0:
        return None

    return (ratio_first - ratio_second) / ratio_first * 100


# intensityType buckets used to classify work vs rest reps.
_WORK_INTENSITIES = {"ACTIVE", "INTERVAL"}
_REST_INTENSITIES = {"REST", "RECOVERY"}


def _classify_workout_structure(lap_dtos: list[dict]) -> str:
    """'steady' | 'interval' を返す。

    REST/RECOVERY と ACTIVE が交互に十分な回数現れれば 'interval'、
    それ以外（単一強度の連続走）は 'steady'。判定不能は 'steady' に
    フォールバック。WARMUP/COOLDOWN や intensityType 欠損 lap は無視する。
    """
    sequence: list[str] = []
    for lap in lap_dtos:
        intensity_type = lap.get("intensityType")
        if not intensity_type:
            continue
        intensity_upper = str(intensity_type).upper()
        if intensity_upper in _WORK_INTENSITIES:
            sequence.append("work")
        elif intensity_upper in _REST_INTENSITIES:
            sequence.append("rest")
        # WARMUP/COOLDOWN/unknown are ignored for structure detection.

    work_count = sequence.count("work")
    rest_count = sequence.count("rest")
    # Need at least 2 work reps and 2 rest segments to be an interval session.
    if work_count < 2 or rest_count < 2:
        return "steady"

    # Repeated work<->rest alternation distinguishes intervals from a single
    # work block bracketed by one rest lap.
    transitions = sum(
        1 for prev, cur in zip(sequence, sequence[1:], strict=False) if prev != cur
    )
    return "interval" if transitions >= 3 else "steady"


def _compute_rep_matched_drift(active_reps: list[dict]) -> float | None:
    """ACTIVE 疾走レップ群について、序盤レップ vs 終盤レップの
    同ペース下HR上昇率% を返す。レップ2本未満 / pace・hr 欠損で None。

    各レップの speed:HR 効率比 (1/pace)/hr を序盤半分 / 終盤半分で平均し、
    drift% = (ratio_early - ratio_late) / ratio_early * 100 を返す。
    同一目標ペース下で終盤のHRが上がる(効率低下)と正値になる。
    """
    import statistics

    valid = [
        r
        for r in active_reps
        if r.get("pace") is not None
        and r["pace"] > 0
        and r.get("hr") is not None
        and r["hr"] > 0
    ]
    if len(valid) < 2:
        return None

    mid = len(valid) // 2
    early_reps = valid[:mid]
    late_reps = valid[mid:]

    def efficiency_ratio(reps: list[dict]) -> float | None:
        if not reps:
            return None
        mean_pace = float(statistics.mean(float(r["pace"]) for r in reps))
        mean_hr = float(statistics.mean(float(r["hr"]) for r in reps))
        if mean_pace <= 0 or mean_hr <= 0:
            return None
        # speed:HR ratio = (1 / pace) / hr
        return (1.0 / mean_pace) / mean_hr

    ratio_early = efficiency_ratio(early_reps)
    ratio_late = efficiency_ratio(late_reps)
    if ratio_early is None or ratio_late is None or ratio_early == 0:
        return None

    return (ratio_early - ratio_late) / ratio_early * 100


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
        phase = PhaseMapper.map_intensity_to_phase(intensity_type)

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

    # Calculate HR drift, branching on workout structure.
    # - steady (single-intensity continuous run): Pa:HR decoupling over the
    #   run-phase laps split into first/second halves (#sub-1).
    # - interval/repetition (ACTIVE<->REST alternation): rep-matched drift over
    #   the ACTIVE work reps only, since a plain time-bisection breaks down when
    #   work and rest laps are interleaved.
    workout_structure = _classify_workout_structure(lap_dtos)
    if workout_structure == "interval":
        result["hr_drift_percentage"] = _compute_rep_matched_drift(run_splits)
    else:
        result["hr_drift_percentage"] = _compute_steady_decoupling(run_splits)

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
    conn: duckdb.DuckDBPyConnection,
    raw_splits_file: str | None = None,
) -> bool:
    """
    Insert performance_trends from raw splits.json into DuckDB performance_trends table.

    Supports both:
    - New 4-phase structure: warmup/run/recovery/cooldown (interval training)

    Steps:
    1. Load raw splits.json
    2. Extract and calculate performance_trends
    3. Detect 4-phase structure
    4. Convert splits arrays to comma-separated strings
    5. Insert into performance_trends table

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

        perf_trends = _extract_performance_trends_from_raw(raw_splits_file)
        if not perf_trends:
            logger.error("Failed to extract performance trends from raw data")
            return False

        # Delete existing record for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM performance_trends WHERE activity_id = ?", [activity_id]
        )

        # Check for 4-phase structure
        has_run_phase = "run_phase" in perf_trends

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

        else:
            logger.error("Unknown phase structure in performance_trends")
            return False

        return True

    except Exception as e:
        logger.error(f"Error inserting performance trends: {e}")
        return False
