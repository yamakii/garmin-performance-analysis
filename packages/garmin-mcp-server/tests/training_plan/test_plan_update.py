"""Tests for TrainingPlanGenerator.update()."""

from datetime import date

import pytest

from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutMatch,
    WorkoutType,
)


def _make_pace_zones():
    return PaceZones(
        easy_low=340.0,
        easy_high=300.0,
        marathon=270.0,
        threshold=255.0,
        interval=234.0,
        repetition=221.0,
    )


def _make_existing_plan(
    plan_id: str = "test-plan",
    version: int = 1,
    total_weeks: int = 4,
) -> TrainingPlan:
    """Create a plan that simulates what comes from the DB."""
    workouts = []
    for week in range(1, total_weeks + 1):
        workouts.append(
            PlannedWorkout(
                workout_id=f"w{version}-{week}-1",
                plan_id=plan_id,
                version=version,
                week_number=week,
                day_of_week=2,
                workout_type=WorkoutType.EASY,
                phase=PeriodizationPhase.BASE,
                workout_date=date(2026, 3, 2 + (week - 1) * 7 + 1),
                target_distance_km=8.0,
            )
        )
        workouts.append(
            PlannedWorkout(
                workout_id=f"w{version}-{week}-2",
                plan_id=plan_id,
                version=version,
                week_number=week,
                day_of_week=4,
                workout_type=WorkoutType.TEMPO,
                phase=PeriodizationPhase.BASE,
                workout_date=date(2026, 3, 2 + (week - 1) * 7 + 3),
                target_distance_km=6.0,
            )
        )
    return TrainingPlan(
        plan_id=plan_id,
        version=version,
        goal_type=GoalType.FITNESS,
        vdot=45.0,
        pace_zones=_make_pace_zones(),
        total_weeks=total_weeks,
        start_date=date(2026, 3, 2),
        weekly_volume_start_km=30.0,
        weekly_volume_peak_km=40.0,
        runs_per_week=4,
        phases=[(PeriodizationPhase.BASE, total_weeks)],
        weekly_volumes=[30 + i * 2.5 for i in range(total_weeks)],
        workouts=workouts,
        status="active",
    )


@pytest.fixture
def mock_fitness_summary():
    from garmin_mcp.training_plan.models import FitnessSummary

    return FitnessSummary(
        vdot=46.0,  # slightly improved
        pace_zones=_make_pace_zones(),
        hr_zones=None,
        weekly_volume_km=35.0,
        runs_per_week=4.0,
        training_type_distribution={"low_moderate": 0.7, "tempo_threshold": 0.3},
        strengths=[],
        weaknesses=[],
    )


@pytest.mark.unit
class TestPlanUpdate:
    def test_update_creates_new_version(self, mocker, mock_fitness_summary):
        """update() should create a plan with version = prev + 1."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        existing_plan = _make_existing_plan()

        mock_reader = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "plan_id": existing_plan.plan_id,
            "version": 1,
            "goal_type": "fitness",
            "total_weeks": 4,
            "start_date": "2026-03-02",
            "vdot": 45.0,
            "pace_zones": _make_pace_zones().model_dump(),
            "weekly_volume_start_km": 30.0,
            "weekly_volume_peak_km": 40.0,
            "runs_per_week": 4,
            "frequency_progression_json": None,
            "target_race_date": None,
            "target_time_seconds": None,
            "status": "active",
            "workouts": [
                {
                    "workout_id": w.workout_id,
                    "plan_id": w.plan_id,
                    "version": w.version,
                    "week_number": w.week_number,
                    "day_of_week": w.day_of_week,
                    "workout_date": str(w.workout_date),
                    "workout_type": w.workout_type.value,
                    "phase": w.phase.value,
                    "target_distance_km": w.target_distance_km,
                    "garmin_workout_id": None,
                    "actual_activity_id": None,
                }
                for w in existing_plan.workouts
            ],
        }
        mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader",
            return_value=mock_reader,
        )

        # Mock matcher: weeks 1 and 2 completed
        mock_matcher = mocker.MagicMock()
        mock_matcher.match_activities.return_value = [
            WorkoutMatch(
                workout_id="w1-1-1", actual_activity_id=1001, activity_date="2026-03-03"
            ),
            WorkoutMatch(
                workout_id="w1-1-2", actual_activity_id=1002, activity_date="2026-03-05"
            ),
            WorkoutMatch(
                workout_id="w1-2-1", actual_activity_id=1003, activity_date="2026-03-10"
            ),
            WorkoutMatch(
                workout_id="w1-2-2", actual_activity_id=1004, activity_date="2026-03-12"
            ),
        ]
        mock_matcher.get_completed_weeks.return_value = ({1, 2}, 2)
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.ActivityMatcher",
            return_value=mock_matcher,
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.update(plan_id="test-plan")

        assert plan.version == 2
        assert plan.plan_id == "test-plan"

    def test_update_preserves_completed_weeks(self, mocker, mock_fitness_summary):
        """Completed week workouts should be copied with actual_activity_id set."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        existing_plan = _make_existing_plan()

        mock_reader = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "plan_id": existing_plan.plan_id,
            "version": 1,
            "goal_type": "fitness",
            "total_weeks": 4,
            "start_date": "2026-03-02",
            "vdot": 45.0,
            "pace_zones": _make_pace_zones().model_dump(),
            "weekly_volume_start_km": 30.0,
            "weekly_volume_peak_km": 40.0,
            "runs_per_week": 4,
            "frequency_progression_json": None,
            "target_race_date": None,
            "target_time_seconds": None,
            "status": "active",
            "workouts": [
                {
                    "workout_id": w.workout_id,
                    "plan_id": w.plan_id,
                    "version": w.version,
                    "week_number": w.week_number,
                    "day_of_week": w.day_of_week,
                    "workout_date": str(w.workout_date),
                    "workout_type": w.workout_type.value,
                    "phase": w.phase.value,
                    "target_distance_km": w.target_distance_km,
                    "garmin_workout_id": None,
                    "actual_activity_id": None,
                }
                for w in existing_plan.workouts
            ],
        }
        mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader",
            return_value=mock_reader,
        )

        # Week 1 completed
        mock_matcher = mocker.MagicMock()
        mock_matcher.match_activities.return_value = [
            WorkoutMatch(
                workout_id="w1-1-1", actual_activity_id=1001, activity_date="2026-03-03"
            ),
            WorkoutMatch(
                workout_id="w1-1-2", actual_activity_id=1002, activity_date="2026-03-05"
            ),
        ]
        mock_matcher.get_completed_weeks.return_value = ({1}, 1)
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.ActivityMatcher",
            return_value=mock_matcher,
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.update(plan_id="test-plan")

        # Week 1 workouts should be preserved with actual_activity_id
        week1 = plan.get_week_workouts(1)
        assert len(week1) == 2
        matched_ids = {w.actual_activity_id for w in week1 if w.actual_activity_id}
        assert matched_ids == {1001, 1002}

        # Weeks 2-4 should be regenerated (no actual_activity_id)
        for week_num in [2, 3, 4]:
            week_workouts = plan.get_week_workouts(week_num)
            assert len(week_workouts) > 0
            for w in week_workouts:
                assert w.actual_activity_id is None

    def test_update_uses_new_fitness(self, mocker, mock_fitness_summary):
        """Updated plan should use new VDOT from reassessed fitness."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        existing_plan = _make_existing_plan()

        mock_reader = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "plan_id": existing_plan.plan_id,
            "version": 1,
            "goal_type": "fitness",
            "total_weeks": 4,
            "start_date": "2026-03-02",
            "vdot": 45.0,
            "pace_zones": _make_pace_zones().model_dump(),
            "weekly_volume_start_km": 30.0,
            "weekly_volume_peak_km": 40.0,
            "runs_per_week": 4,
            "frequency_progression_json": None,
            "target_race_date": None,
            "target_time_seconds": None,
            "status": "active",
            "workouts": [
                {
                    "workout_id": w.workout_id,
                    "plan_id": w.plan_id,
                    "version": w.version,
                    "week_number": w.week_number,
                    "day_of_week": w.day_of_week,
                    "workout_date": str(w.workout_date),
                    "workout_type": w.workout_type.value,
                    "phase": w.phase.value,
                    "target_distance_km": w.target_distance_km,
                    "garmin_workout_id": None,
                    "actual_activity_id": None,
                }
                for w in existing_plan.workouts
            ],
        }
        mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader",
            return_value=mock_reader,
        )

        mock_matcher = mocker.MagicMock()
        mock_matcher.match_activities.return_value = []
        mock_matcher.get_completed_weeks.return_value = (set(), 0)
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.ActivityMatcher",
            return_value=mock_matcher,
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.update(plan_id="test-plan")

        # Should use new VDOT (46.0 from mock_fitness_summary)
        assert plan.vdot == 46.0

    def test_update_calls_insert_with_previous_version(
        self, mocker, mock_fitness_summary
    ):
        """update() should call insert_training_plan with previous_version."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mock_insert = mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        existing_plan = _make_existing_plan()

        mock_reader = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "plan_id": existing_plan.plan_id,
            "version": 1,
            "goal_type": "fitness",
            "total_weeks": 4,
            "start_date": "2026-03-02",
            "vdot": 45.0,
            "pace_zones": _make_pace_zones().model_dump(),
            "weekly_volume_start_km": 30.0,
            "weekly_volume_peak_km": 40.0,
            "runs_per_week": 4,
            "frequency_progression_json": None,
            "target_race_date": None,
            "target_time_seconds": None,
            "status": "active",
            "workouts": [
                {
                    "workout_id": w.workout_id,
                    "plan_id": w.plan_id,
                    "version": w.version,
                    "week_number": w.week_number,
                    "day_of_week": w.day_of_week,
                    "workout_date": str(w.workout_date),
                    "workout_type": w.workout_type.value,
                    "phase": w.phase.value,
                    "target_distance_km": w.target_distance_km,
                    "garmin_workout_id": None,
                    "actual_activity_id": None,
                }
                for w in existing_plan.workouts
            ],
        }
        mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader",
            return_value=mock_reader,
        )

        mock_matcher = mocker.MagicMock()
        mock_matcher.match_activities.return_value = []
        mock_matcher.get_completed_weeks.return_value = (set(), 0)
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.ActivityMatcher",
            return_value=mock_matcher,
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        generator.update(plan_id="test-plan")

        # Verify insert was called with previous_version=1
        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args
        assert call_kwargs[1].get("previous_version") == 1 or (
            len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == 1
        )

    def test_update_supersedes_old_version(self, mocker, mock_fitness_summary):
        """The old plan should remain as-is (inserter handles status change)."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        existing_plan = _make_existing_plan()

        mock_reader = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "plan_id": existing_plan.plan_id,
            "version": 1,
            "goal_type": "fitness",
            "total_weeks": 4,
            "start_date": "2026-03-02",
            "vdot": 45.0,
            "pace_zones": _make_pace_zones().model_dump(),
            "weekly_volume_start_km": 30.0,
            "weekly_volume_peak_km": 40.0,
            "runs_per_week": 4,
            "frequency_progression_json": None,
            "target_race_date": None,
            "target_time_seconds": None,
            "status": "active",
            "workouts": [
                {
                    "workout_id": w.workout_id,
                    "plan_id": w.plan_id,
                    "version": w.version,
                    "week_number": w.week_number,
                    "day_of_week": w.day_of_week,
                    "workout_date": str(w.workout_date),
                    "workout_type": w.workout_type.value,
                    "phase": w.phase.value,
                    "target_distance_km": w.target_distance_km,
                    "garmin_workout_id": None,
                    "actual_activity_id": None,
                }
                for w in existing_plan.workouts
            ],
        }
        mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader",
            return_value=mock_reader,
        )

        mock_matcher = mocker.MagicMock()
        mock_matcher.match_activities.return_value = []
        mock_matcher.get_completed_weeks.return_value = (set(), 0)
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.ActivityMatcher",
            return_value=mock_matcher,
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.update(plan_id="test-plan")

        assert plan.status == "active"
        assert plan.version == 2
