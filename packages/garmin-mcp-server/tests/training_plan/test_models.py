"""Tests for training plan models."""

from datetime import date

import pytest

from garmin_mcp.training_plan.models import (
    FitnessSummary,
    GoalType,
    HRZones,
    IntervalDetail,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutType,
)


@pytest.mark.unit
class TestGoalType:
    def test_race_types(self):
        assert GoalType.RACE_5K == "race_5k"
        assert GoalType.RACE_10K == "race_10k"
        assert GoalType.RACE_HALF == "race_half"
        assert GoalType.RACE_FULL == "race_full"
        assert GoalType.FITNESS == "fitness"

    def test_from_string(self):
        assert GoalType("race_5k") == GoalType.RACE_5K


@pytest.mark.unit
class TestPaceZones:
    def test_valid_zones(self):
        zones = PaceZones(
            easy_low=360,
            easy_high=330,
            marathon=300,
            threshold=270,
            interval=240,
            repetition=210,
        )
        assert zones.easy_low == 360
        assert zones.repetition == 210

    def test_negative_pace_rejected(self):
        with pytest.raises(ValueError, match="Pace must be positive"):
            PaceZones(
                easy_low=-1,
                easy_high=330,
                marathon=300,
                threshold=270,
                interval=240,
                repetition=210,
            )

    def test_serialization_roundtrip(self):
        zones = PaceZones(
            easy_low=360,
            easy_high=330,
            marathon=300,
            threshold=270,
            interval=240,
            repetition=210,
        )
        data = zones.model_dump()
        zones2 = PaceZones(**data)
        assert zones == zones2


@pytest.mark.unit
class TestHRZones:
    def test_valid_zones(self):
        zones = HRZones(
            easy_low=120,
            easy_high=140,
            marathon_low=140,
            marathon_high=155,
            threshold_low=155,
            threshold_high=170,
        )
        assert zones.easy_low == 120
        assert zones.threshold_high == 170


@pytest.mark.unit
class TestFitnessSummary:
    def test_minimal(self):
        summary = FitnessSummary(
            vdot=45.0,
            pace_zones=PaceZones(
                easy_low=360,
                easy_high=330,
                marathon=300,
                threshold=270,
                interval=240,
                repetition=210,
            ),
            weekly_volume_km=30.0,
            runs_per_week=4.0,
        )
        assert summary.vdot == 45.0
        assert summary.strengths == []
        assert summary.weaknesses == []
        assert summary.hr_zones is None

    def test_with_all_fields(self):
        summary = FitnessSummary(
            vdot=50.0,
            pace_zones=PaceZones(
                easy_low=340,
                easy_high=310,
                marathon=280,
                threshold=255,
                interval=228,
                repetition=200,
            ),
            hr_zones=HRZones(
                easy_low=120,
                easy_high=140,
                marathon_low=140,
                marathon_high=155,
                threshold_low=155,
                threshold_high=170,
            ),
            weekly_volume_km=50.0,
            runs_per_week=5.0,
            training_type_distribution={"easy": 0.6, "tempo": 0.2, "interval": 0.2},
            strengths=["endurance"],
            weaknesses=["speed"],
        )
        assert summary.training_type_distribution["easy"] == 0.6


@pytest.mark.unit
class TestIntervalDetail:
    def test_valid_interval(self):
        interval = IntervalDetail(
            repetitions=6,
            work_distance_m=800,
            work_pace_low=230,
            work_pace_high=220,
            recovery_duration_minutes=2.0,
        )
        assert interval.repetitions == 6
        assert interval.recovery_type == "jog"

    def test_minimum_repetitions(self):
        with pytest.raises(ValueError):
            IntervalDetail(repetitions=0, recovery_duration_minutes=1.0)


@pytest.mark.unit
class TestPlannedWorkout:
    def test_minimal_workout(self):
        workout = PlannedWorkout(
            plan_id="test-plan",
            week_number=1,
            day_of_week=2,
            workout_type=WorkoutType.EASY,
            phase=PeriodizationPhase.BASE,
        )
        assert workout.workout_type == WorkoutType.EASY
        assert workout.workout_id  # auto-generated
        assert workout.garmin_workout_id is None

    def test_full_workout(self):
        workout = PlannedWorkout(
            plan_id="test-plan",
            week_number=3,
            day_of_week=6,
            workout_type=WorkoutType.INTERVAL,
            target_distance_km=10.0,
            target_pace_low=270,
            target_pace_high=250,
            phase=PeriodizationPhase.BUILD,
            intervals=IntervalDetail(
                repetitions=5,
                work_distance_m=1000,
                work_pace_low=240,
                work_pace_high=230,
                recovery_duration_minutes=2.0,
            ),
            warmup_minutes=10.0,
            cooldown_minutes=10.0,
        )
        assert workout.intervals is not None
        assert workout.intervals.repetitions == 5

    def test_day_of_week_validation(self):
        with pytest.raises(ValueError):
            PlannedWorkout(
                plan_id="test",
                week_number=1,
                day_of_week=8,
                workout_type=WorkoutType.EASY,
                phase=PeriodizationPhase.BASE,
            )


@pytest.mark.unit
class TestTrainingPlan:
    @pytest.fixture
    def sample_plan(self):
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
                plan_id="plan-1",
                week_number=1,
                day_of_week=2,
                workout_type=WorkoutType.EASY,
                phase=PeriodizationPhase.BASE,
            ),
            PlannedWorkout(
                plan_id="plan-1",
                week_number=1,
                day_of_week=4,
                workout_type=WorkoutType.TEMPO,
                phase=PeriodizationPhase.BASE,
            ),
            PlannedWorkout(
                plan_id="plan-1",
                week_number=2,
                day_of_week=2,
                workout_type=WorkoutType.EASY,
                phase=PeriodizationPhase.BASE,
            ),
        ]
        return TrainingPlan(
            plan_id="plan-1",
            goal_type=GoalType.RACE_10K,
            target_race_date=date(2026, 6, 1),
            vdot=45.0,
            pace_zones=pace_zones,
            total_weeks=12,
            start_date=date(2026, 3, 9),
            weekly_volume_start_km=30.0,
            weekly_volume_peak_km=50.0,
            runs_per_week=4,
            phases=[
                (PeriodizationPhase.BASE, 5),
                (PeriodizationPhase.BUILD, 4),
                (PeriodizationPhase.PEAK, 2),
                (PeriodizationPhase.TAPER, 1),
            ],
            weekly_volumes=[30 + i * 1.5 for i in range(12)],
            workouts=workouts,
        )

    def test_get_week_workouts(self, sample_plan):
        week1 = sample_plan.get_week_workouts(1)
        assert len(week1) == 2
        week2 = sample_plan.get_week_workouts(2)
        assert len(week2) == 1

    def test_get_phase_for_week(self, sample_plan):
        assert sample_plan.get_phase_for_week(1) == PeriodizationPhase.BASE
        assert sample_plan.get_phase_for_week(5) == PeriodizationPhase.BASE
        assert sample_plan.get_phase_for_week(6) == PeriodizationPhase.BUILD
        assert sample_plan.get_phase_for_week(10) == PeriodizationPhase.PEAK
        assert sample_plan.get_phase_for_week(12) == PeriodizationPhase.TAPER

    def test_to_summary(self, sample_plan):
        summary = sample_plan.to_summary()
        assert summary["plan_id"] == "plan-1"
        assert summary["goal_type"] == "race_10k"
        assert summary["total_workouts"] == 3
        assert "workouts" not in summary

    def test_weeks_validation(self):
        with pytest.raises(ValueError):
            TrainingPlan(
                plan_id="bad",
                goal_type=GoalType.FITNESS,
                vdot=40.0,
                pace_zones=PaceZones(
                    easy_low=360,
                    easy_high=330,
                    marathon=300,
                    threshold=270,
                    interval=240,
                    repetition=210,
                ),
                total_weeks=2,  # Too short
                start_date=date(2026, 1, 1),
                weekly_volume_start_km=20.0,
                weekly_volume_peak_km=40.0,
                runs_per_week=4,
                phases=[],
                weekly_volumes=[],
            )

    def test_serialization_roundtrip(self, sample_plan):
        data = sample_plan.model_dump(mode="json")
        plan2 = TrainingPlan(**data)
        assert plan2.plan_id == sample_plan.plan_id
        assert len(plan2.workouts) == len(sample_plan.workouts)
        assert plan2.goal_type == sample_plan.goal_type
