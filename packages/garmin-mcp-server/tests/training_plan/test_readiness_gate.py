"""Tests for the readiness gate (quality-workout downgrade)."""

from __future__ import annotations

from datetime import date

import pytest

from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutType,
)
from garmin_mcp.training_plan.readiness_gate import apply_readiness_gate


def _workout(
    workout_type: WorkoutType,
    week_number: int = 1,
    day_of_week: int = 3,
) -> PlannedWorkout:
    return PlannedWorkout(
        workout_id=f"w-{workout_type.value}-{week_number}-{day_of_week}",
        plan_id="plan-1",
        week_number=week_number,
        day_of_week=day_of_week,
        workout_type=workout_type,
        phase=PeriodizationPhase.BASE,
        workout_date=date(2026, 3, 3),
    )


# overall_flag=True corresponds to e.g. HRV today=48 below band mean60 SD8.
_FLAGGED = {"overall_flag": True}
# overall_flag=False corresponds to e.g. HRV today=58 within band.
_WITHIN_BAND = {"overall_flag": False}


@pytest.mark.unit
def test_gate_downgrades_tempo_when_flagged() -> None:
    workouts = [_workout(WorkoutType.TEMPO)]

    result, notes = apply_readiness_gate(_FLAGGED, workouts)

    assert result[0].workout_type == WorkoutType.EASY
    assert len(notes) == 1


@pytest.mark.unit
def test_gate_downgrades_interval_to_recovery() -> None:
    workouts = [_workout(WorkoutType.INTERVAL)]

    result, notes = apply_readiness_gate(_FLAGGED, workouts)

    assert result[0].workout_type == WorkoutType.RECOVERY
    assert len(notes) == 1


@pytest.mark.unit
def test_gate_noop_when_within_band() -> None:
    workouts = [_workout(WorkoutType.TEMPO)]

    result, notes = apply_readiness_gate(_WITHIN_BAND, workouts)

    assert result is workouts
    assert result[0].workout_type == WorkoutType.TEMPO
    assert notes == []


@pytest.mark.unit
def test_gate_only_affects_weeks_to_check() -> None:
    workouts = [
        _workout(WorkoutType.TEMPO, week_number=1),
        _workout(WorkoutType.TEMPO, week_number=2),
    ]

    result, notes = apply_readiness_gate(_FLAGGED, workouts, weeks_to_check=1)

    assert result[0].workout_type == WorkoutType.EASY
    assert result[1].workout_type == WorkoutType.TEMPO
    assert len(notes) == 1


@pytest.mark.unit
def test_gate_preserves_easy_long_rest() -> None:
    workouts = [
        _workout(WorkoutType.EASY),
        _workout(WorkoutType.LONG_RUN),
        _workout(WorkoutType.REST),
    ]

    result, notes = apply_readiness_gate(_FLAGGED, workouts)

    assert [w.workout_type for w in result] == [
        WorkoutType.EASY,
        WorkoutType.LONG_RUN,
        WorkoutType.REST,
    ]
    assert notes == []


@pytest.mark.integration
def test_e2e_readiness_gate_persists_downgrade(tmp_path) -> None:
    """Gate-downgraded workout_type survives a save -> read round trip."""
    from garmin_mcp.database.db_writer import GarminDBWriter
    from garmin_mcp.database.inserters.training_plans import insert_training_plan
    from garmin_mcp.database.readers.training_plans import TrainingPlanReader

    db_path = str(tmp_path / "test.duckdb")
    GarminDBWriter(db_path=db_path)  # Creates all tables via _ensure_tables()

    threshold_day = date(2026, 3, 5)
    workouts = [
        PlannedWorkout(
            workout_id="w-threshold",
            plan_id="plan-557",
            week_number=1,
            day_of_week=4,
            workout_type=WorkoutType.THRESHOLD,
            phase=PeriodizationPhase.BASE,
            workout_date=threshold_day,
        ),
    ]

    gated, notes = apply_readiness_gate({"overall_flag": True}, workouts)
    assert len(notes) == 1

    plan = TrainingPlan(
        plan_id="plan-557",
        version=1,
        goal_type=GoalType.FITNESS,
        vdot=45.0,
        pace_zones=PaceZones(
            easy_low=360,
            easy_high=330,
            marathon=300,
            threshold=270,
            interval=240,
            repetition=210,
        ),
        total_weeks=4,
        start_date=date(2026, 3, 2),
        weekly_volume_start_km=30.0,
        weekly_volume_peak_km=40.0,
        runs_per_week=4,
        phases=[(PeriodizationPhase.BASE, 4)],
        weekly_volumes=[30, 33, 36, 40],
        workouts=gated,
    )

    insert_training_plan(db_path, plan)

    reader = TrainingPlanReader(db_path=db_path)
    result = reader.get_training_plan("plan-557", week_number=1)

    saved = next(
        w for w in result["workouts"] if str(w["workout_date"]) == str(threshold_day)
    )
    assert saved["workout_type"] == "easy"
