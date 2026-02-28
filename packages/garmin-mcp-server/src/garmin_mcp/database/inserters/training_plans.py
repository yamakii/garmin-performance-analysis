"""Training plan DB inserter."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from garmin_mcp.training_plan.models import TrainingPlan

logger = logging.getLogger(__name__)


def insert_training_plan(
    db_path: str | None,
    plan: TrainingPlan,
    previous_version: int | None = None,
) -> None:
    """Insert training plan and workouts into DuckDB (versioned).

    Args:
        db_path: Path to DuckDB database. If None, uses default.
        plan: TrainingPlan to insert.
        previous_version: If set, marks the previous version as 'superseded'
            and inserts the new plan as the next version. If None, uses
            DELETE + INSERT pattern for the same plan_id and version.
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    with get_write_connection(db_path) as conn:
        if previous_version is not None:
            # UPDATE mode: mark old version as superseded, insert new version
            conn.execute(
                "UPDATE training_plans SET status = 'superseded' "
                "WHERE plan_id = ? AND version = ?",
                [plan.plan_id, previous_version],
            )
        else:
            # NEW mode: delete existing data for this plan_id and version
            conn.execute(
                "DELETE FROM planned_workouts WHERE plan_id = ? AND version = ?",
                [plan.plan_id, plan.version],
            )
            conn.execute(
                "DELETE FROM training_plans WHERE plan_id = ? AND version = ?",
                [plan.plan_id, plan.version],
            )

        # Insert plan
        conn.execute(
            """
            INSERT INTO training_plans (
                plan_id, version, goal_type, target_race_date, target_time_seconds,
                vdot, pace_zones_json, total_weeks, start_date,
                weekly_volume_start_km, weekly_volume_peak_km,
                runs_per_week, frequency_progression_json,
                personalization_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                plan.plan_id,
                plan.version,
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
                    workout_id, plan_id, version, week_number, day_of_week,
                    workout_date, workout_type, description_ja,
                    target_distance_km, target_duration_minutes,
                    target_pace_low, target_pace_high,
                    target_hr_low, target_hr_high,
                    intervals_json, phase
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    w.workout_id,
                    w.plan_id,
                    w.version,
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

        logger.info(
            f"Saved plan {plan.plan_id} v{plan.version} with {len(plan.workouts)} workouts"
        )
