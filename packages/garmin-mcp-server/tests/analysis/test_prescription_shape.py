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
