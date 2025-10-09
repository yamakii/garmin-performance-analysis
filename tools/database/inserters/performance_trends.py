"""
PerformanceTrendsInserter - Insert performance_trends from performance.json to DuckDB

Inserts phase-based performance analysis (warmup/main/finish) into performance_trends table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_performance_trends(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert performance_trends from performance.json into DuckDB performance_trends table.

    Supports both:
    - New 4-phase structure: warmup/run/recovery/cooldown (interval training)
    - Legacy 3-phase structure: warmup/main/finish (regular runs)

    Steps:
    1. Load performance.json
    2. Extract performance_trends
    3. Detect phase structure (3-phase or 4-phase)
    4. Convert splits arrays to comma-separated strings
    5. Insert into performance_trends table

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

        # Extract performance_trends
        perf_trends = performance_data.get("performance_trends")
        if not perf_trends or not isinstance(perf_trends, dict):
            logger.error(f"No performance_trends found in {performance_file}")
            return False

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

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

            # Insert with 4-phase data
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
                    recovery_splits,
                    recovery_avg_pace_seconds_per_km,
                    recovery_avg_pace_str,
                    recovery_avg_hr,
                    cooldown_splits,
                    cooldown_avg_pace_seconds_per_km,
                    cooldown_avg_pace_str,
                    cooldown_avg_hr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    run_phase.get("avg_pace"),
                    format_pace(run_phase.get("avg_pace")),
                    run_phase.get("avg_hr"),
                    recovery_splits,
                    recovery_phase.get("avg_pace"),
                    format_pace(recovery_phase.get("avg_pace")),
                    recovery_phase.get("avg_hr"),
                    cooldown_splits,
                    cooldown_phase.get("avg_pace"),
                    format_pace(cooldown_phase.get("avg_pace")),
                    cooldown_phase.get("avg_hr"),
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
