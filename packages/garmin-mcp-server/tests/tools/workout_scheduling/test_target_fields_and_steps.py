"""HR target fields (ceiling-only defaults) and build_steps() per prescription type."""

from __future__ import annotations

import pytest

from garmin_mcp.tools.workout_scheduling import (
    _target_fields,
    build_steps_from_prescription,
    build_workout_json,
)


@pytest.mark.unit
def test_target_fields_hr_high_only_defaults_floor() -> None:
    """A ceiling-only step still gets an HR-range target, with a non-alerting
    floor of 80 bpm so the low-HR alert can never push the pace up."""
    fields = _target_fields({"hr_high": 150})

    assert fields["targetType"]["workoutTargetTypeId"] == 4
    assert fields["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert fields["targetValueOne"] == 80
    assert fields["targetValueTwo"] == 150


@pytest.mark.unit
def test_target_fields_both_bounds_unchanged() -> None:
    """An explicit floor (quality sessions) is passed through untouched."""
    fields = _target_fields({"hr_low": 162, "hr_high": 169})

    assert fields["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert fields["targetValueOne"] == 162
    assert fields["targetValueTwo"] == 169


@pytest.mark.unit
def test_target_fields_hr_low_only_is_no_target() -> None:
    """A floor without a ceiling carries no target (unchanged behaviour)."""
    fields = _target_fields({"hr_low": 130})

    assert fields["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "targetValueOne" not in fields
    assert "targetValueTwo" not in fields


@pytest.mark.unit
def test_build_workout_json_long_run_ceiling_only_has_hr_target_on_body_step() -> None:
    """A ceiling-governed long run uploads with an 80-150 bpm target on the body
    step, while the untargeted warmup/cooldown stay on no.target."""
    result = build_workout_json(
        "Long 120min (Z2 ceiling 150)",
        [
            {"step_type": "warmup", "duration_minutes": 10},
            {"step_type": "run", "duration_minutes": 120, "hr_high": 150},
            {"step_type": "cooldown", "duration_minutes": 5},
        ],
    )

    warmup, body, cooldown = result["workoutSegments"][0]["workoutSteps"]
    assert body["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert body["targetValueOne"] == 80
    assert body["targetValueTwo"] == 150
    assert warmup["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert cooldown["targetType"]["workoutTargetTypeKey"] == "no.target"


@pytest.mark.unit
def test_build_steps_long_km_ceiling_only() -> None:
    """A distance-prescribed long run is a single body step with a ceiling-only
    HR target — no bookends inflating the prescribed distance (#1039)."""
    steps = build_steps_from_prescription(
        {"session_type": "long", "target_km": 22.0, "hr_high": 150}
    )

    assert len(steps) == 1
    (body,) = steps
    assert body["step_type"] == "run"
    assert body["distance_m"] == 22000
    assert body["hr_high"] == 150
    assert "hr_low" not in body


@pytest.mark.unit
def test_build_steps_easy_minutes() -> None:
    """A time-prescribed easy run is one step ending on duration, not distance."""
    steps = build_steps_from_prescription(
        {"session_type": "easy", "target_minutes": 45, "hr_high": 150}
    )

    assert len(steps) == 1
    body = steps[0]
    assert body["duration_minutes"] == 45
    assert "distance_m" not in body
    assert body["hr_high"] == 150


@pytest.mark.unit
def test_build_steps_recovery_single_step_keeps_floor_when_prescribed() -> None:
    """A recovery run stays single-step but keeps a floor when one is prescribed."""
    steps = build_steps_from_prescription(
        {
            "session_type": "recovery",
            "target_minutes": 30,
            "hr_low": 110,
            "hr_high": 140,
        }
    )

    assert len(steps) == 1
    body = steps[0]
    assert body["duration_minutes"] == 30
    assert body["hr_low"] == 110
    assert body["hr_high"] == 140


@pytest.mark.unit
def test_build_steps_threshold_both_bounds() -> None:
    """A quality session keeps its bookends and its prescribed floor + ceiling."""
    steps = build_steps_from_prescription(
        {
            "session_type": "threshold",
            "target_minutes": 20,
            "hr_low": 162,
            "hr_high": 169,
        }
    )

    assert len(steps) == 3
    assert steps[0] == {"step_type": "warmup", "duration_minutes": 10}
    assert steps[2] == {"step_type": "cooldown", "duration_minutes": 5}
    body = steps[1]
    assert body["duration_minutes"] == 20
    assert body["hr_low"] == 162
    assert body["hr_high"] == 169


@pytest.mark.unit
def test_build_steps_strides_repeat_group() -> None:
    """Strides need no target: they become a 5x(20s / 90s) repeat group."""
    steps = build_steps_from_prescription({"session_type": "strides"})

    group = steps[1]
    assert group["repeat_count"] == 5
    assert group["steps"] == [
        {"step_type": "run", "duration_seconds": 20},
        {"step_type": "recovery", "duration_seconds": 90},
    ]


@pytest.mark.unit
def test_build_steps_rejects_rest() -> None:
    """A rest day is prescribed but never registered as a run."""
    with pytest.raises(ValueError, match="not registrable"):
        build_steps_from_prescription({"session_type": "rest"})


@pytest.mark.unit
def test_build_steps_rejects_no_target() -> None:
    """A run without any target cannot become a workout."""
    with pytest.raises(ValueError, match="target_minutes or target_km"):
        build_steps_from_prescription({"session_type": "easy"})
