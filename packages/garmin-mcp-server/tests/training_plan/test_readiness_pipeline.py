"""Cross-feature E2E for the readiness pipeline (#562).

Exercises the full chain that #555 (deviation) and #557 (gate) only cover in
isolation: insert ``daily_wellness`` history -> ``get_wellness_baseline_deviation``
-> ``apply_readiness_gate`` -> ``insert_training_plan`` ->
``TrainingPlanReader.get_training_plan``. Asserts a low-HRV day downgrades a
week-1 quality workout *and* the downgrade survives persistence, while a
within-band day passes through untouched.

A single tmp DuckDB (tables created by ``GarminDBWriter``) backs both the
wellness read and the plan round trip. No real data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.training_plans import insert_training_plan
from garmin_mcp.database.readers.training_plans import TrainingPlanReader
from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutType,
)
from garmin_mcp.training_plan.readiness_gate import apply_readiness_gate

# History HRV band: cycling this 7-value set keeps mean ~= 60, pstdev ~= 8, so a
# today value of 48 lands ~1.5 SD below (low/adverse) and 58 stays within.
_HRV_BAND = [48.0, 52.0, 56.0, 60.0, 64.0, 68.0, 72.0]


def _insert_wellness_history(db_path: Path, *, hrv_today: float) -> None:
    """Insert 30 history days (HRV band mean~60 SD~8) + today with ``hrv_today``.

    Readiness and resting HR are held constant so only HRV can drive the flag.
    """
    base = datetime(2026, 6, 1)
    conn = duckdb.connect(str(db_path))
    try:
        for i in range(30):
            d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO daily_wellness "
                "(wellness_id, date, resting_hr, hrv_overnight_ms, "
                "training_readiness) VALUES (?, ?, ?, ?, ?)",
                [i + 1, d, 50, _HRV_BAND[i % len(_HRV_BAND)], 70],
            )
        today = (base + timedelta(days=30)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO daily_wellness "
            "(wellness_id, date, resting_hr, hrv_overnight_ms, "
            "training_readiness) VALUES (?, ?, ?, ?, ?)",
            [31, today, 50, hrv_today, 70],
        )
    finally:
        conn.close()


def _threshold_plan(workouts: list[PlannedWorkout]) -> TrainingPlan:
    return TrainingPlan(
        plan_id="plan-562",
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
        start_date=date(2026, 6, 29),
        weekly_volume_start_km=30.0,
        weekly_volume_peak_km=40.0,
        runs_per_week=4,
        phases=[(PeriodizationPhase.BASE, 4)],
        weekly_volumes=[30, 33, 36, 40],
        workouts=workouts,
    )


def _week1_threshold() -> PlannedWorkout:
    return PlannedWorkout(
        workout_id="w-threshold",
        plan_id="plan-562",
        week_number=1,
        day_of_week=4,
        workout_type=WorkoutType.THRESHOLD,
        phase=PeriodizationPhase.BASE,
        workout_date=date(2026, 7, 2),
    )


@pytest.mark.integration
def test_e2e_pipeline_flag_to_downgrade(tmp_path: Path) -> None:
    """Low-HRV day -> overall_flag True -> week-1 threshold downgraded to easy
    and the downgrade survives save -> read."""
    db_path = tmp_path / "test.duckdb"
    GarminDBWriter(db_path=str(db_path))  # creates all tables

    _insert_wellness_history(db_path, hrv_today=48.0)

    deviation = GarminDBReader(db_path=str(db_path)).get_wellness_baseline_deviation()
    assert deviation["overall_flag"] is True
    assert deviation["hrv"]["flag"] == "low"

    gated, notes = apply_readiness_gate(deviation, [_week1_threshold()])
    assert len(notes) == 1
    assert gated[0].workout_type == WorkoutType.EASY

    insert_training_plan(str(db_path), _threshold_plan(gated))

    reader = TrainingPlanReader(db_path=str(db_path))
    result = reader.get_training_plan("plan-562", week_number=1)
    saved = next(
        w for w in result["workouts"] if str(w["workout_date"]) == "2026-07-02"
    )
    assert saved["workout_type"] == "easy"


@pytest.mark.integration
def test_e2e_pipeline_within_band_no_change(tmp_path: Path) -> None:
    """Within-band day -> overall_flag False -> gate is a no-op and the week-1
    threshold stays 'threshold' after save -> read."""
    db_path = tmp_path / "test.duckdb"
    GarminDBWriter(db_path=str(db_path))  # creates all tables

    _insert_wellness_history(db_path, hrv_today=58.0)

    deviation = GarminDBReader(db_path=str(db_path)).get_wellness_baseline_deviation()
    assert deviation["overall_flag"] is False
    assert deviation["hrv"]["flag"] == "within"

    gated, notes = apply_readiness_gate(deviation, [_week1_threshold()])
    assert notes == []
    assert gated[0].workout_type == WorkoutType.THRESHOLD

    insert_training_plan(str(db_path), _threshold_plan(gated))

    reader = TrainingPlanReader(db_path=str(db_path))
    result = reader.get_training_plan("plan-562", week_number=1)
    saved = next(
        w for w in result["workouts"] if str(w["workout_date"]) == "2026-07-02"
    )
    assert saved["workout_type"] == "threshold"
