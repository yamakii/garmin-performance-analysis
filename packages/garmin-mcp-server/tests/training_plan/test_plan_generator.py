"""Tests for TrainingPlanGenerator."""

import pytest

from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    TrainingPlan,
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
