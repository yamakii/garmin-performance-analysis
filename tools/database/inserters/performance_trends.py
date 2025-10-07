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

    Steps:
    1. Load performance.json
    2. Extract performance_trends
    3. Convert splits arrays to comma-separated strings
    4. Insert into performance_trends table

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

        # Ensure performance_trends table exists
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
                main_splits VARCHAR,
                main_avg_pace_seconds_per_km DOUBLE,
                main_avg_pace_str VARCHAR,
                main_avg_hr DOUBLE,
                main_avg_cadence DOUBLE,
                main_avg_power DOUBLE,
                main_evaluation VARCHAR,
                finish_splits VARCHAR,
                finish_avg_pace_seconds_per_km DOUBLE,
                finish_avg_pace_str VARCHAR,
                finish_avg_hr DOUBLE,
                finish_avg_cadence DOUBLE,
                finish_avg_power DOUBLE,
                finish_evaluation VARCHAR
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute(
            "DELETE FROM performance_trends WHERE activity_id = ?", [activity_id]
        )

        # Extract phase data
        warmup_phase = perf_trends.get("warmup_phase", {})
        main_phase = perf_trends.get("main_phase", {})
        finish_phase = perf_trends.get("finish_phase", {})

        # Convert splits arrays to comma-separated strings
        warmup_splits = ",".join(str(s) for s in warmup_phase.get("splits", []))
        main_splits = ",".join(str(s) for s in main_phase.get("splits", []))
        finish_splits = ",".join(str(s) for s in finish_phase.get("splits", []))

        # Helper function to format pace
        def format_pace(pace_seconds):
            if pace_seconds is None:
                return None
            minutes = int(pace_seconds // 60)
            seconds = int(pace_seconds % 60)
            return f"{minutes}:{seconds:02d}"

        # Insert performance trends data
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
                main_splits,
                main_avg_pace_seconds_per_km,
                main_avg_pace_str,
                main_avg_hr,
                finish_splits,
                finish_avg_pace_seconds_per_km,
                finish_avg_pace_str,
                finish_avg_hr
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
                main_splits,
                main_phase.get("avg_pace"),
                format_pace(main_phase.get("avg_pace")),
                main_phase.get("avg_hr"),
                finish_splits,
                finish_phase.get("avg_pace"),
                format_pace(finish_phase.get("avg_pace")),
                finish_phase.get("avg_hr"),
            ],
        )

        conn.close()

        logger.info(
            f"Successfully inserted performance trends data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting performance trends: {e}")
        return False
