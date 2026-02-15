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
                "displayOrder": 6,
            }
        }
        if pace_low and pace_high:
            target["targetValueOne"] = GarminWorkoutBuilder._pace_to_speed(pace_low)
            target["targetValueTwo"] = GarminWorkoutBuilder._pace_to_speed(pace_high)
        return target

    @staticmethod
    def _distance_condition(distance_km: float) -> tuple[dict, float]:
        """Create distance end condition. Returns (condition_dict, value)."""
        return (
            {
                "conditionTypeId": 3,
                "conditionTypeKey": "distance",
                "displayOrder": 3,
                "displayable": True,
            },
            distance_km * 1000,  # meters
        )

    @staticmethod
    def _time_condition(minutes: float) -> tuple[dict, float]:
        """Create time end condition. Returns (condition_dict, value)."""
        return (
            {
                "conditionTypeId": 2,
                "conditionTypeKey": "time",
                "displayOrder": 2,
                "displayable": True,
            },
            minutes * 60,  # seconds
        )

    @staticmethod
    def _lap_button_condition() -> tuple[dict, None]:
        """Create lap button (open) end condition. Returns (condition_dict, None)."""
        return (
            {
                "conditionTypeId": 1,
                "conditionTypeKey": "lap.button",
                "displayOrder": 1,
                "displayable": True,
            },
            None,
        )

    @staticmethod
    def _build_simple_workout(workout: PlannedWorkout) -> list[dict]:
        """Build single-segment workout (easy, recovery, long run)."""
        end_cond, end_val = GarminWorkoutBuilder._distance_condition(
            workout.target_distance_km or 5.0
        )
        step: dict[str, Any] = {
            "type": "ExecutableStepDTO",
            "stepOrder": 1,
            "stepType": {
                "stepTypeId": 3,
                "stepTypeKey": "interval",
                "displayOrder": 3,
            },
            "endCondition": end_cond,
            "endConditionValue": end_val,
            "category": "RUN",
            "exerciseName": "RUN",
            **GarminWorkoutBuilder._speed_target(
                workout.target_pace_low, workout.target_pace_high
            ),
        }
        return [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": [step],
            }
        ]

    @staticmethod
    def _build_structured_workout(workout: PlannedWorkout) -> list[dict]:
        """Build warmup + main + cooldown workout (tempo, threshold)."""
        steps: list[dict[str, Any]] = []
        order = 1

        # Warmup
        if workout.warmup_minutes:
            wu_cond, wu_val = GarminWorkoutBuilder._time_condition(
                workout.warmup_minutes
            )
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {
                        "stepTypeId": 1,
                        "stepTypeKey": "warmUp",
                        "displayOrder": 1,
                    },
                    "endCondition": wu_cond,
                    "endConditionValue": wu_val,
                    "category": "RUN",
                    "exerciseName": "RUN",
                }
            )
            order += 1

        # Main segment
        main_cond, main_val = GarminWorkoutBuilder._distance_condition(
            workout.target_distance_km or 5.0
        )
        steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": order,
                "stepType": {
                    "stepTypeId": 3,
                    "stepTypeKey": "interval",
                    "displayOrder": 3,
                },
                "endCondition": main_cond,
                "endConditionValue": main_val,
                "category": "RUN",
                "exerciseName": "RUN",
                **GarminWorkoutBuilder._speed_target(
                    workout.target_pace_low, workout.target_pace_high
                ),
            }
        )
        order += 1

        # Cooldown
        if workout.cooldown_minutes:
            cd_cond, cd_val = GarminWorkoutBuilder._time_condition(
                workout.cooldown_minutes
            )
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {
                        "stepTypeId": 2,
                        "stepTypeKey": "coolDown",
                        "displayOrder": 2,
                    },
                    "endCondition": cd_cond,
                    "endConditionValue": cd_val,
                    "category": "RUN",
                    "exerciseName": "RUN",
                }
            )

        return [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": steps,
            }
        ]

    @staticmethod
    def _build_interval_workout(workout: PlannedWorkout) -> list[dict]:
        """Build interval workout with repeat group."""
        if not workout.intervals:
            return GarminWorkoutBuilder._build_simple_workout(workout)

        steps: list[dict[str, Any]] = []
        order = 1
        iv = workout.intervals

        # Warmup
        if workout.warmup_minutes:
            wu_cond, wu_val = GarminWorkoutBuilder._time_condition(
                workout.warmup_minutes
            )
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {
                        "stepTypeId": 1,
                        "stepTypeKey": "warmUp",
                        "displayOrder": 1,
                    },
                    "endCondition": wu_cond,
                    "endConditionValue": wu_val,
                    "category": "RUN",
                    "exerciseName": "RUN",
                }
            )
            order += 1

        # Repeat group
        repeat_steps: list[dict[str, Any]] = []

        # Work interval
        if iv.work_distance_m:
            work_cond, work_val = GarminWorkoutBuilder._distance_condition(
                iv.work_distance_m / 1000
            )
        else:
            work_cond, work_val = GarminWorkoutBuilder._time_condition(
                iv.work_duration_minutes or 3
            )
        repeat_steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": 1,
                "stepType": {
                    "stepTypeId": 3,
                    "stepTypeKey": "interval",
                    "displayOrder": 3,
                },
                "endCondition": work_cond,
                "endConditionValue": work_val,
                "category": "RUN",
                "exerciseName": "RUN",
                **GarminWorkoutBuilder._speed_target(
                    iv.work_pace_low, iv.work_pace_high
                ),
            }
        )

        # Recovery
        rec_cond, rec_val = GarminWorkoutBuilder._time_condition(
            iv.recovery_duration_minutes
        )
        repeat_steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": 2,
                "stepType": {
                    "stepTypeId": 4,
                    "stepTypeKey": "recovery",
                    "displayOrder": 4,
                },
                "endCondition": rec_cond,
                "endConditionValue": rec_val,
                "category": "RUN",
                "exerciseName": "RUN",
            }
        )

        steps.append(
            {
                "type": "RepeatGroupDTO",
                "stepOrder": order,
                "stepType": {
                    "stepTypeId": 6,
                    "stepTypeKey": "repeat",
                    "displayOrder": 6,
                },
                "numberOfIterations": iv.repetitions,
                "workoutSteps": repeat_steps,
            }
        )
        order += 1

        # Cooldown
        if workout.cooldown_minutes:
            cd_cond, cd_val = GarminWorkoutBuilder._time_condition(
                workout.cooldown_minutes
            )
            steps.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepOrder": order,
                    "stepType": {
                        "stepTypeId": 2,
                        "stepTypeKey": "coolDown",
                        "displayOrder": 2,
                    },
                    "endCondition": cd_cond,
                    "endConditionValue": cd_val,
                    "category": "RUN",
                    "exerciseName": "RUN",
                }
            )

        return [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": steps,
            }
        ]
