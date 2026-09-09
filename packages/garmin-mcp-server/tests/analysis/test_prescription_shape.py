"""Tests for the shared workout shape constants (#1039).

``bookend_minutes`` is the single number the workout builder and the reconciler
must agree on, so it gets its own table-driven test.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.prescription_shape import (
    BOOKENDED_TYPES,
    COOLDOWN_MINUTES,
    WARMUP_MINUTES,
    bookend_minutes,
    bookend_minutes_from_steps,
)


@pytest.mark.unit
def test_bookend_minutes_quality_types() -> None:
    """Quality sessions are registered with a 10min warmup + 5min cooldown."""
    assert set(BOOKENDED_TYPES) == {"threshold", "tempo", "strides"}
    assert WARMUP_MINUTES + COOLDOWN_MINUTES == 15
    for session_type in ("threshold", "tempo", "strides"):
        assert bookend_minutes(session_type) == 15


@pytest.mark.unit
def test_bookend_minutes_easy_types_and_none() -> None:
    """Easy-effort sessions (and unknown/None types) carry no bookends."""
    for session_type in ("easy", "long", "recovery", "rest", None):
        assert bookend_minutes(session_type) == 0


@pytest.mark.unit
def test_bookend_minutes_from_steps_hand_built_buildup() -> None:
    """A hand-built buildup's real bookends are read off its steps (#1087).

    The 2026-09-09 tempo: 10min warmup, five 1km steps, 10min cooldown — 20
    minutes, not the constant 15 the session type alone would claim.
    """
    steps = [
        {"step_type": "warmup", "duration_minutes": 10},
        *[{"step_type": "run", "distance_m": 1000} for _ in range(5)],
        {"step_type": "cooldown", "duration_minutes": 10},
    ]

    assert bookend_minutes_from_steps(steps) == 20
    assert bookend_minutes("tempo") == 15


@pytest.mark.unit
def test_bookend_minutes_from_steps_matches_constant_for_standard_shape() -> None:
    """The builder's own output still measures the documented 15 minutes."""
    from garmin_mcp.tools.workout_scheduling import build_steps_from_prescription

    tempo = build_steps_from_prescription(
        {"session_type": "tempo", "target_minutes": 31, "hr_low": 162, "hr_high": 169}
    )
    strides = build_steps_from_prescription({"session_type": "strides"})
    easy = build_steps_from_prescription(
        {"session_type": "easy", "target_minutes": 45, "hr_high": 150}
    )

    assert bookend_minutes_from_steps(tempo) == 15
    assert bookend_minutes_from_steps(strides) == 15
    assert bookend_minutes_from_steps(easy) == 0


@pytest.mark.unit
def test_bookend_minutes_from_steps_counts_seconds_and_ignores_repeats() -> None:
    """Second-based bookends convert; a repeat group is body work, not a bookend."""
    steps = [
        {"step_type": "warmup", "duration_seconds": 540},
        {
            "repeat_count": 5,
            "steps": [
                {"step_type": "run", "duration_seconds": 20},
                {"step_type": "recovery", "duration_seconds": 90},
            ],
        },
        {"step_type": "cooldown", "duration_seconds": 360},
    ]

    assert bookend_minutes_from_steps(steps) == 15


@pytest.mark.unit
def test_bookend_minutes_from_steps_without_steps_is_none() -> None:
    """No steps means nothing to record, so the constant stays in charge."""
    assert bookend_minutes_from_steps(None) is None
    assert bookend_minutes_from_steps([]) is None
