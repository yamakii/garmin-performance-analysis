"""Training plan DB inserter."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from garmin_mcp.training_plan.models import TrainingPlan

logger = logging.getLogger(__name__)


def insert_training_plan(db_path: str | None, plan: TrainingPlan) -> None:
    """Insert training plan and workouts into DuckDB.

    Uses DELETE + INSERT pattern (same as other inserters).
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    conn = duckdb.connect(db_path)

    try:
        # Ensure tables exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_plans (
                plan_id VARCHAR PRIMARY KEY,
                goal_type VARCHAR NOT NULL,
                target_race_date DATE,
                target_time_seconds INTEGER,
                vdot DOUBLE NOT NULL,
                pace_zones_json VARCHAR NOT NULL,
                total_weeks INTEGER NOT NULL,
                start_date DATE NOT NULL,
                weekly_volume_start_km DOUBLE NOT NULL,
                weekly_volume_peak_km DOUBLE NOT NULL,
                runs_per_week INTEGER NOT NULL,
                frequency_progression_json VARCHAR,
                personalization_notes VARCHAR,
                status VARCHAR DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS planned_workouts (
                workout_id VARCHAR PRIMARY KEY,
                plan_id VARCHAR NOT NULL,
                week_number INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                workout_date DATE,
                workout_type VARCHAR NOT NULL,
                description_ja VARCHAR,
                target_distance_km DOUBLE,
                target_duration_minutes DOUBLE,
                target_pace_low DOUBLE,
                target_pace_high DOUBLE,
                target_hr_low INTEGER,
                target_hr_high INTEGER,
                intervals_json VARCHAR,
                phase VARCHAR NOT NULL,
                garmin_workout_id BIGINT,
                uploaded_at TIMESTAMP,
                actual_activity_id BIGINT,
                adherence_score DOUBLE,
                completed_at TIMESTAMP
            )
        """)

        # Delete existing plan data
        conn.execute("DELETE FROM planned_workouts WHERE plan_id = ?", [plan.plan_id])
        conn.execute("DELETE FROM training_plans WHERE plan_id = ?", [plan.plan_id])

        # Insert plan
        conn.execute(
            """
            INSERT INTO training_plans (
                plan_id, goal_type, target_race_date, target_time_seconds,
                vdot, pace_zones_json, total_weeks, start_date,
                weekly_volume_start_km, weekly_volume_peak_km,
                runs_per_week, frequency_progression_json,
                personalization_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                plan.plan_id,
                plan.goal_type.value,
                str(plan.target_race_date) if plan.target_race_date else None,
                plan.target_time_seconds,
                plan.vdot,
                plan.pace_zones.model_dump_json(),
                plan.total_weeks,
                str(plan.start_date),
                plan.weekly_volume_start_km,
                plan.weekly_volume_peak_km,
                plan.runs_per_week,
                (
                    json.dumps(plan.frequency_progression)
                    if plan.frequency_progression
                    else None
                ),
                plan.personalization_notes,
                plan.status,
            ],
        )

        # Insert workouts
        for w in plan.workouts:
            intervals_json = w.intervals.model_dump_json() if w.intervals else None
            conn.execute(
                """
                INSERT INTO planned_workouts (
                    workout_id, plan_id, week_number, day_of_week,
                    workout_date, workout_type, description_ja,
                    target_distance_km, target_duration_minutes,
                    target_pace_low, target_pace_high,
                    target_hr_low, target_hr_high,
                    intervals_json, phase
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    w.workout_id,
                    w.plan_id,
                    w.week_number,
                    w.day_of_week,
                    str(w.workout_date) if w.workout_date else None,
                    w.workout_type.value,
                    w.description_ja,
                    w.target_distance_km,
                    w.target_duration_minutes,
                    w.target_pace_low,
                    w.target_pace_high,
                    w.target_hr_low,
                    w.target_hr_high,
                    intervals_json,
                    w.phase.value,
                ],
            )

        logger.info(f"Saved plan {plan.plan_id} with {len(plan.workouts)} workouts")
    finally:
        conn.close()
