"""Tests for GarminWorkoutBuilder."""

import pytest

from garmin_mcp.training_plan.models import (
    IntervalDetail,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    WorkoutType,
)
from garmin_mcp.training_plan.workout_builder import GarminWorkoutBuilder


@pytest.fixture
def pace_zones():
    return PaceZones(
        easy_low=360.0,
        easy_high=300.0,
        marathon=276.0,
        threshold=255.0,
        interval=234.0,
        repetition=221.0,
    )


def _make_workout(wt, **kwargs):
    """Helper to create a PlannedWorkout."""
    defaults = {
        "plan_id": "test",
        "week_number": 1,
        "day_of_week": 1,
        "workout_type": wt,
        "phase": PeriodizationPhase.BASE,
        "target_distance_km": 5.0,
        "target_pace_low": 360.0,
        "target_pace_high": 300.0,
    }
    defaults.update(kwargs)
    return PlannedWorkout(**defaults)


@pytest.mark.unit
class TestGarminWorkoutBuilder:
    def test_build_easy_workout(self, pace_zones):
        workout = _make_workout(WorkoutType.EASY)
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        assert result["workoutName"] is not None
        assert result["sportType"]["sportTypeKey"] == "running"
        assert len(result["workoutSegments"]) == 1
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["stepType"]["stepTypeKey"] == "interval"

    def test_build_long_run_workout(self, pace_zones):
        workout = _make_workout(WorkoutType.LONG_RUN, target_distance_km=15.0)
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        steps = result["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["endCondition"]["conditionValue"] == 15000  # 15km in meters

    def test_build_tempo_has_warmup_cooldown(self, pace_zones):
        workout = _make_workout(
            WorkoutType.TEMPO,
            warmup_minutes=10.0,
            cooldown_minutes=10.0,
            target_pace_low=265.0,
            target_pace_high=255.0,
        )
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 3
        assert steps[0]["stepType"]["stepTypeKey"] == "warmUp"
        assert steps[1]["stepType"]["stepTypeKey"] == "interval"
        assert steps[2]["stepType"]["stepTypeKey"] == "coolDown"

    def test_build_interval_workout(self, pace_zones):
        intervals = IntervalDetail(
            repetitions=5,
            work_distance_m=1000,
            work_pace_low=239.0,
            work_pace_high=229.0,
            recovery_duration_minutes=3.0,
        )
        workout = _make_workout(
            WorkoutType.INTERVAL,
            warmup_minutes=10.0,
            cooldown_minutes=10.0,
            intervals=intervals,
        )
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        steps = result["workoutSegments"][0]["workoutSteps"]
        # warmup + repeat group + cooldown
        assert len(steps) == 3
        assert steps[0]["stepType"]["stepTypeKey"] == "warmUp"
        assert steps[1]["type"] == "RepeatGroupDTO"
        assert steps[1]["numberOfIterations"] == 5
        assert steps[2]["stepType"]["stepTypeKey"] == "coolDown"

        # Check repeat group has work + recovery
        repeat_steps = steps[1]["workoutSteps"]
        assert len(repeat_steps) == 2
        assert repeat_steps[0]["stepType"]["stepTypeKey"] == "interval"
        assert repeat_steps[1]["stepType"]["stepTypeKey"] == "recovery"

    def test_speed_conversion(self):
        # 300 sec/km = 3.333 m/s
        speed = GarminWorkoutBuilder._pace_to_speed(300.0)
        assert abs(speed - 3.333) < 0.01

        # 240 sec/km = 4.167 m/s
        speed = GarminWorkoutBuilder._pace_to_speed(240.0)
        assert abs(speed - 4.167) < 0.01

    def test_speed_target_order(self, pace_zones):
        """targetValueOne should be lower speed (slower pace)."""
        workout = _make_workout(
            WorkoutType.EASY,
            target_pace_low=360.0,  # slower (lower speed)
            target_pace_high=300.0,  # faster (higher speed)
        )
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        step = result["workoutSegments"][0]["workoutSteps"][0]
        # targetValueOne = slower pace → lower speed value
        assert step["targetValueOne"] < step["targetValueTwo"]

    def test_interval_without_details_fallback(self, pace_zones):
        """Interval workout without IntervalDetail should fallback to simple."""
        workout = _make_workout(WorkoutType.INTERVAL, intervals=None)
        result = GarminWorkoutBuilder.build(workout, pace_zones)

        steps = result["workoutSegments"][0]["workoutSteps"]
        # Falls back to simple workout (1 step)
        assert len(steps) == 1
