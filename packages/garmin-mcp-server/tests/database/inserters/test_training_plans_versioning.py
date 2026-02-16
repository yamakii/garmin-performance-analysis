"""Tests for versioned training plan insertion."""

from datetime import date

import duckdb
import pytest

from garmin_mcp.database.inserters.training_plans import insert_training_plan
from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutType,
)


def _make_plan(
    plan_id: str = "plan-1",
    version: int = 1,
    status: str = "active",
) -> TrainingPlan:
    """Create a minimal test plan."""
    pace_zones = PaceZones(
        easy_low=360,
        easy_high=330,
        marathon=300,
        threshold=270,
        interval=240,
        repetition=210,
    )
    workouts = [
        PlannedWorkout(
            workout_id=f"w{version}-1",
            plan_id=plan_id,
            version=version,
            week_number=1,
            day_of_week=2,
            workout_type=WorkoutType.EASY,
            phase=PeriodizationPhase.BASE,
            workout_date=date(2026, 3, 3),
        ),
        PlannedWorkout(
            workout_id=f"w{version}-2",
            plan_id=plan_id,
            version=version,
            week_number=1,
            day_of_week=4,
            workout_type=WorkoutType.TEMPO,
            phase=PeriodizationPhase.BASE,
            workout_date=date(2026, 3, 5),
        ),
    ]
    return TrainingPlan(
        plan_id=plan_id,
        version=version,
        goal_type=GoalType.FITNESS,
        vdot=45.0,
        pace_zones=pace_zones,
        total_weeks=4,
        start_date=date(2026, 3, 2),
        weekly_volume_start_km=30.0,
        weekly_volume_peak_km=40.0,
        runs_per_week=4,
        phases=[(PeriodizationPhase.BASE, 4)],
        weekly_volumes=[30, 33, 36, 40],
        workouts=workouts,
        status=status,
    )


@pytest.mark.unit
class TestInsertTrainingPlanVersioning:
    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test.duckdb")

    def test_new_plan_has_version_1(self, db_path):
        """New plan should be saved with version=1."""
        plan = _make_plan()
        insert_training_plan(db_path, plan)

        conn = duckdb.connect(db_path)
        row = conn.execute(
            "SELECT version, status FROM training_plans WHERE plan_id = 'plan-1'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 1
        assert row[1] == "active"

    def test_workouts_have_version(self, db_path):
        """Workouts should be saved with version column."""
        plan = _make_plan()
        insert_training_plan(db_path, plan)

        conn = duckdb.connect(db_path)
        rows = conn.execute(
            "SELECT version FROM planned_workouts WHERE plan_id = 'plan-1'"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert all(r[0] == 1 for r in rows)

    def test_update_creates_new_version(self, db_path):
        """Updating a plan creates version 2, sets v1 to superseded."""
        # Insert v1
        plan_v1 = _make_plan(version=1)
        insert_training_plan(db_path, plan_v1)

        # Insert v2 with previous_version
        plan_v2 = _make_plan(version=2)
        insert_training_plan(db_path, plan_v2, previous_version=1)

        conn = duckdb.connect(db_path)

        # v1 should be superseded
        v1_row = conn.execute(
            "SELECT status FROM training_plans WHERE plan_id = 'plan-1' AND version = 1"
        ).fetchone()
        assert v1_row is not None
        assert v1_row[0] == "superseded"

        # v2 should be active
        v2_row = conn.execute(
            "SELECT status FROM training_plans WHERE plan_id = 'plan-1' AND version = 2"
        ).fetchone()
        assert v2_row is not None
        assert v2_row[0] == "active"

        # Both versions' workouts exist
        v1_workouts = conn.execute(
            "SELECT COUNT(*) FROM planned_workouts WHERE plan_id = 'plan-1' AND version = 1"
        ).fetchone()
        v2_workouts = conn.execute(
            "SELECT COUNT(*) FROM planned_workouts WHERE plan_id = 'plan-1' AND version = 2"
        ).fetchone()
        conn.close()

        assert v1_workouts[0] == 2  # not deleted
        assert v2_workouts[0] == 2

    def test_old_version_data_preserved(self, db_path):
        """Old version data should NOT be deleted on update."""
        plan_v1 = _make_plan(version=1)
        insert_training_plan(db_path, plan_v1)

        plan_v2 = _make_plan(version=2)
        insert_training_plan(db_path, plan_v2, previous_version=1)

        conn = duckdb.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM training_plans WHERE plan_id = 'plan-1'"
        ).fetchone()
        conn.close()

        assert count[0] == 2  # both versions exist

    def test_new_plan_replaces_same_version(self, db_path):
        """Re-inserting without previous_version replaces existing v1."""
        plan_v1 = _make_plan(version=1)
        insert_training_plan(db_path, plan_v1)
        insert_training_plan(db_path, plan_v1)  # re-insert same version

        conn = duckdb.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM training_plans WHERE plan_id = 'plan-1'"
        ).fetchone()
        conn.close()

        assert count[0] == 1  # only one version
