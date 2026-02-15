"""Builds Garmin Connect RunningWorkout objects from PlannedWorkout."""

from __future__ import annotations

import logging
from typing import Any

from garmin_mcp.training_plan.models import PaceZones, PlannedWorkout, WorkoutType

logger = logging.getLogger(__name__)


class GarminWorkoutBuilder:
    """Converts PlannedWorkout to garminconnect RunningWorkout format."""

    @staticmethod
    def build(workout: PlannedWorkout, pace_zones: PaceZones) -> dict[str, Any]:
        """Build a Garmin workout dict from a PlannedWorkout.

        Returns a dict compatible with garminconnect's workout API.
        The dict structure follows the Garmin Connect workout format:
        {
            "workoutName": str,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [...]
        }

        Speed conversion: pace (sec/km) → speed (m/s) = 1000 / pace_sec_per_km
        targetValueOne = slower pace (lower speed)
        targetValueTwo = faster pace (higher speed)
        """
        wt = workout.workout_type
        name = workout.description_ja or f"Week{workout.week_number} {wt.value}"

        if wt in (WorkoutType.EASY, WorkoutType.RECOVERY, WorkoutType.LONG_RUN):
            segments = GarminWorkoutBuilder._build_simple_workout(workout)
        elif wt in (WorkoutType.TEMPO, WorkoutType.THRESHOLD, WorkoutType.RACE_PACE):
            segments = GarminWorkoutBuilder._build_structured_workout(workout)
        elif wt in (WorkoutType.INTERVAL, WorkoutType.REPETITION):
            segments = GarminWorkoutBuilder._build_interval_workout(workout)
        else:
            segments = GarminWorkoutBuilder._build_simple_workout(workout)

        return {
            "workoutName": name,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": segments,
        }

    @staticmethod
    def _pace_to_speed(pace_sec_per_km: float) -> float:
        """Convert pace (sec/km) to speed (m/s)."""
        if pace_sec_per_km <= 0:
            return 0
        return 1000.0 / pace_sec_per_km

    @staticmethod
    def _speed_target(
        pace_low: float | None, pace_high: float | None
    ) -> dict[str, object]:
        """Create speed target dict. pace_low = slower pace (lower speed)."""
        target: dict[str, object] = {
            "targetType": {
                "workoutTargetTypeId": 6,
                "workoutTargetTypeKey": "speed.zone",
            }
        }
        if pace_low and pace_high:
            target["targetValueOne"] = GarminWorkoutBuilder._pace_to_speed(pace_low)
            target["targetValueTwo"] = GarminWorkoutBuilder._pace_to_speed(pace_high)
        return target

    @staticmethod
    def _distance_condition(distance_km: float) -> dict:
        """Create distance end condition."""
        return {
            "conditionTypeId": 3,
            "conditionTypeKey": "distance",
            "conditionValue": distance_km * 1000,  # meters
        }

    @staticmethod
    def _time_condition(minutes: float) -> dict:
        """Create time end condition."""
        return {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "conditionValue": minutes * 60,  # seconds
        }

    @staticmethod
    def _lap_button_condition() -> dict:
        """Create lap button (open) end condition."""
        return {
            "conditionTypeId": 1,
            "conditionTypeKey": "lap.button",
        }

    @staticmethod
    def _build_simple_workout(workout: PlannedWorkout) -> list[dict]:
        """Build single-segment workout (easy, recovery, long run)."""
        step = {
            "type": "ExecutableStepDTO",
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": GarminWorkoutBuilder._distance_condition(
                workout.target_distance_km or 5.0
            ),
            **GarminWorkoutBuilder._speed_target(
                workout.target_pace_low, workout.target_pace_high
            ),
        }
        return [
            {"segmentOrder": 1, "sportType": {"sportTypeId": 1}, "workoutSteps": [step]}
        ]

    @staticmethod
    def _build_structured_workout(workout: PlannedWorkout) -> list[dict]:
        """Build warmup + main + cooldown workout (tempo, threshold)."""
        steps = []
        order = 1

        # Warmup
        if workout.warmup_minutes:
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {"stepTypeId": 1, "stepTypeKey": "warmUp"},
                    "endCondition": GarminWorkoutBuilder._time_condition(
                        workout.warmup_minutes
                    ),
                }
            )
            order += 1

        # Main segment
        steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": order,
                "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                "endCondition": GarminWorkoutBuilder._distance_condition(
                    workout.target_distance_km or 5.0
                ),
                **GarminWorkoutBuilder._speed_target(
                    workout.target_pace_low, workout.target_pace_high
                ),
            }
        )
        order += 1

        # Cooldown
        if workout.cooldown_minutes:
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {"stepTypeId": 2, "stepTypeKey": "coolDown"},
                    "endCondition": GarminWorkoutBuilder._time_condition(
                        workout.cooldown_minutes
                    ),
                }
            )

        return [
            {"segmentOrder": 1, "sportType": {"sportTypeId": 1}, "workoutSteps": steps}
        ]

    @staticmethod
    def _build_interval_workout(workout: PlannedWorkout) -> list[dict]:
        """Build interval workout with repeat group."""
        if not workout.intervals:
            return GarminWorkoutBuilder._build_simple_workout(workout)

        steps = []
        order = 1
        iv = workout.intervals

        # Warmup
        if workout.warmup_minutes:
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {"stepTypeId": 1, "stepTypeKey": "warmUp"},
                    "endCondition": GarminWorkoutBuilder._time_condition(
                        workout.warmup_minutes
                    ),
                }
            )
            order += 1

        # Repeat group
        repeat_steps = []

        # Work interval
        work_condition = (
            GarminWorkoutBuilder._distance_condition(iv.work_distance_m / 1000)
            if iv.work_distance_m
            else GarminWorkoutBuilder._time_condition(iv.work_duration_minutes or 3)
        )
        repeat_steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": 1,
                "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                "endCondition": work_condition,
                **GarminWorkoutBuilder._speed_target(
                    iv.work_pace_low, iv.work_pace_high
                ),
            }
        )

        # Recovery
        repeat_steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": 2,
                "stepType": {"stepTypeId": 4, "stepTypeKey": "recovery"},
                "endCondition": GarminWorkoutBuilder._time_condition(
                    iv.recovery_duration_minutes
                ),
            }
        )

        steps.append(
            {
                "type": "RepeatGroupDTO",
                "stepOrder": order,
                "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
                "numberOfIterations": iv.repetitions,
                "workoutSteps": repeat_steps,
            }
        )
        order += 1

        # Cooldown
        if workout.cooldown_minutes:
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {"stepTypeId": 2, "stepTypeKey": "coolDown"},
                    "endCondition": GarminWorkoutBuilder._time_condition(
                        workout.cooldown_minutes
                    ),
                }
            )

        return [
            {"segmentOrder": 1, "sportType": {"sportTypeId": 1}, "workoutSteps": steps}
        ]
