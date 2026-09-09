"""build_workout_json(): step shapes, repeat groups, distance steps, title prefix."""

from __future__ import annotations

import pytest

from garmin_mcp.tools.workout_scheduling import (
    build_workout_json,
)


@pytest.mark.unit
def test_build_workout_json_single_step_hr_range() -> None:
    """A single 120-min run with a 130-152 bpm range yields a time end-condition
    of 7200s and targetValueOne/Two = 130/152."""
    result = build_workout_json(
        "Long 120min",
        [{"step_type": "run", "duration_minutes": 120, "hr_low": 130, "hr_high": 152}],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["endCondition"]["conditionTypeKey"] == "time"
    assert step["endConditionValue"] == 7200
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["targetValueOne"] == 130
    assert step["targetValueTwo"] == 152


@pytest.mark.unit
def test_build_workout_json_warmup_work_cooldown() -> None:
    """A warmup/run/cooldown trio gets stepOrder 1,2,3 with the right stepTypes."""
    result = build_workout_json(
        "Threshold",
        [
            {"step_type": "warmup", "duration_minutes": 15},
            {"step_type": "run", "duration_minutes": 20, "hr_low": 153, "hr_high": 165},
            {"step_type": "cooldown", "duration_minutes": 10},
        ],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    assert [s["stepOrder"] for s in steps] == [1, 2, 3]
    assert [s["stepType"]["stepTypeKey"] for s in steps] == [
        "warmup",
        "interval",
        "cooldown",
    ]


@pytest.mark.unit
def test_build_workout_json_repeat_group() -> None:
    """A repeat_count=6 group becomes a RepeatGroupDTO with 6 iterations and 2
    child steps."""
    result = build_workout_json(
        "Strides",
        [
            {"step_type": "warmup", "duration_minutes": 10},
            {
                "repeat_count": 6,
                "steps": [
                    {"step_type": "run", "distance_m": 100},
                    {"step_type": "recovery", "duration_seconds": 60},
                ],
            },
            {"step_type": "cooldown", "duration_minutes": 10},
        ],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    group = steps[1]
    assert group["type"] == "RepeatGroupDTO"
    assert group["numberOfIterations"] == 6
    assert group["endConditionValue"] == 6.0
    assert len(group["workoutSteps"]) == 2
    assert group["workoutSteps"][0]["stepType"]["stepTypeKey"] == "interval"
    assert group["workoutSteps"][1]["stepType"]["stepTypeKey"] == "recovery"


@pytest.mark.unit
def test_build_workout_json_distance_step() -> None:
    """A distance_m step yields a distance end-condition of 100."""
    result = build_workout_json(
        "Repeat",
        [{"step_type": "run", "distance_m": 100}],
    )

    step = result["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["endConditionValue"] == 100


@pytest.mark.unit
def test_title_prefix_enforced() -> None:
    """The workoutName is force-prefixed with '[MCP] ' without doubling it."""
    plain = build_workout_json("Long 120min", [{"step_type": "run", "distance_m": 1}])
    assert plain["workoutName"] == "[MCP] Long 120min"

    already = build_workout_json(
        "[MCP] Long 120min", [{"step_type": "run", "distance_m": 1}]
    )
    assert already["workoutName"] == "[MCP] Long 120min"
