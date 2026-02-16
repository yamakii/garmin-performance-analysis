"""Tests for TrainingPlanGenerator."""

import pytest

from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    TrainingPlan,
    WorkoutType,
)


@pytest.fixture
def mock_fitness_summary():
    """Create a mock FitnessSummary."""
    from garmin_mcp.training_plan.models import FitnessSummary

    return FitnessSummary(
        vdot=45.0,
        pace_zones=PaceZones(
            easy_low=340.0,
            easy_high=300.0,
            marathon=270.0,
            threshold=255.0,
            interval=234.0,
            repetition=221.0,
        ),
        hr_zones=None,
        weekly_volume_km=30.0,
        runs_per_week=3.5,
        training_type_distribution={"low_moderate": 0.7, "tempo_threshold": 0.3},
        strengths=[],
        weaknesses=[],
    )


@pytest.mark.unit
class TestPlanGenerator:
    def test_generate_race_plan(self, mocker, mock_fitness_summary):
        """Generate a race plan with mocked fitness assessor."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.insert_training_plan",
            create=True,
        )
        # Patch the lazy import inside generate()
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_10k",
            total_weeks=12,
            runs_per_week=4,
        )

        assert isinstance(plan, TrainingPlan)
        assert plan.goal_type == GoalType.RACE_10K
        assert plan.total_weeks == 12
        assert plan.runs_per_week == 4
        assert len(plan.workouts) > 0
        assert plan.vdot > 0

    def test_generate_fitness_plan(self, mocker, mock_fitness_summary):
        """Generate a fitness plan."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="fitness",
            total_weeks=8,
            runs_per_week=3,
        )

        assert plan.goal_type == GoalType.FITNESS
        assert plan.total_weeks == 8
        assert len(plan.workouts) > 0

    def test_generate_with_target_time(self, mocker, mock_fitness_summary):
        """Target time adjusts VDOT upward if higher than current."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_5k",
            total_weeks=12,
            target_time_seconds=1100,  # Aggressive target (~18:20)
        )

        # Should use higher VDOT from target time
        assert plan.vdot >= mock_fitness_summary.vdot

    def test_plan_has_correct_phases(self, mocker, mock_fitness_summary):
        """Race plan should have all 4 phases."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_10k",
            total_weeks=16,
        )

        phase_types = {p for p, _ in plan.phases}
        assert PeriodizationPhase.BASE in phase_types
        assert PeriodizationPhase.BUILD in phase_types
        assert PeriodizationPhase.PEAK in phase_types
        assert PeriodizationPhase.TAPER in phase_types

    def test_weekly_volumes_match_total_weeks(self, mocker, mock_fitness_summary):
        """Weekly volumes list length should match total weeks."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_5k",
            total_weeks=12,
        )

        assert len(plan.weekly_volumes) == 12

    def test_workout_dates_are_calculated(self, mocker, mock_fitness_summary):
        """Workouts should have workout_date calculated from start_date."""
        from datetime import date, timedelta

        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_5k",
            total_weeks=4,
            target_race_date="2026-04-01",
        )

        # All workouts should have dates assigned
        for w in plan.workouts:
            assert w.workout_date is not None, f"Workout {w.workout_id} has no date"

        # Verify date calculation: start_date + (week-1)*7 + (day-1)
        start_date = date.fromisoformat("2026-04-01") - timedelta(weeks=4)
        for w in plan.workouts:
            expected = start_date + timedelta(
                weeks=w.week_number - 1, days=w.day_of_week - 1
            )
            assert w.workout_date == expected, (
                f"Week {w.week_number}, day {w.day_of_week}: "
                f"expected {expected}, got {w.workout_date}"
            )

    def test_generate_return_to_run_plan(self, mocker, mock_fitness_summary):
        """Return-to-run plan should use conservative phases."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=8,
            runs_per_week=3,
        )

        assert plan.goal_type == GoalType.RETURN_TO_RUN
        assert plan.total_weeks == 8
        assert len(plan.workouts) > 0

        # First phase should be RECOVERY
        assert plan.phases[0][0] == PeriodizationPhase.RECOVERY

        # No threshold or interval workouts in first half
        first_half_workouts = [w for w in plan.workouts if w.week_number <= 4]
        for w in first_half_workouts:
            assert w.workout_type not in (
                WorkoutType.THRESHOLD,
                WorkoutType.INTERVAL,
                WorkoutType.REPETITION,
            ), f"Week {w.week_number} has {w.workout_type} in RECOVERY phase"

    def test_return_to_run_conservative_peak_volume(self, mocker, mock_fitness_summary):
        """Return-to-run peak volume should be conservative (1.3x start)."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=8,
            runs_per_week=3,
        )

        # Peak should be ~1.3x start, not 1.5x
        ratio = plan.weekly_volume_peak_km / plan.weekly_volume_start_km
        assert (
            ratio <= 1.35
        ), f"Peak/start ratio {ratio:.2f} is too aggressive for return_to_run"

    def test_workout_dates_within_plan_range(self, mocker, mock_fitness_summary):
        """All workout dates should fall within the plan's date range."""
        from datetime import date, timedelta

        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_10k",
            total_weeks=8,
            target_race_date="2026-05-01",
        )

        race_date = date.fromisoformat("2026-05-01")
        start_date = race_date - timedelta(weeks=8)

        for w in plan.workouts:
            assert w.workout_date is not None
            assert w.workout_date >= start_date
            assert w.workout_date < race_date


@pytest.mark.unit
class TestPlanGeneratorFrequencyProgression:
    def test_generate_with_start_frequency(self, mocker, mock_fitness_summary):
        """start_frequency generates frequency_progression correctly."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=4,
            runs_per_week=6,
            start_frequency=3,
        )

        assert plan.frequency_progression is not None
        assert len(plan.frequency_progression) == 4
        assert plan.frequency_progression[0] == 3
        assert plan.frequency_progression[-1] == 6
        # Week 1 should have 3 workouts, week 4 should have 6
        week1 = plan.get_week_workouts(1)
        week4 = plan.get_week_workouts(4)
        assert len(week1) == 3
        assert len(week4) == 6

    def test_generate_without_start_frequency_backward_compat(
        self, mocker, mock_fitness_summary
    ):
        """Without start_frequency, frequency_progression is None (backward compat)."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="race_10k",
            total_weeks=12,
            runs_per_week=4,
        )

        assert plan.frequency_progression is None
        # All weeks should have 4 workouts
        for week_num in range(1, 13):
            assert plan.get_week_frequency(week_num) == 4

    def test_return_to_run_auto_frequency_progression(
        self, mocker, mock_fitness_summary
    ):
        """return_to_run: RECOVERY at runs_per_week, BASE at runs_per_week+1."""
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = mock_fitness_summary

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=8,
            runs_per_week=4,
        )

        # Auto: start_frequency=4 (RECOVERY), runs_per_week=5 (BASE)
        assert plan.frequency_progression is not None
        assert plan.frequency_progression[0] == 4
        assert plan.frequency_progression[-1] == 5
        # RECOVERY weeks have 4 runs, BASE weeks have 5 runs
        assert plan.get_week_frequency(1) == 4
        assert plan.get_week_frequency(8) == 5
