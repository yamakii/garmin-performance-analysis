"""Tests for the run purpose resolver (Issue #1312)."""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.run_purpose import (
    DEFAULT_PURPOSE_BY_SESSION,
    PURPOSES,
    resolve_purpose,
)

pytestmark = pytest.mark.unit


def test_resolve_purpose_prescription_wins() -> None:
    """A declared purpose beats both the session default and the run's data."""
    resolved = resolve_purpose(
        {"session_type": "long", "purpose": "long_goal_pace"},
        {"moving_minutes": 120, "intensity_class": 1},
    )
    assert resolved.id == "long_goal_pace"
    assert resolved.source == "prescription"
    assert resolved.label_ja == PURPOSES["long_goal_pace"].label_ja


def test_resolve_purpose_session_default() -> None:
    """A long row without a purpose resolves to long_easy."""
    resolved = resolve_purpose({"session_type": "long", "purpose": None}, {})
    assert resolved.id == "long_easy"
    assert resolved.source == "session_default"


def test_resolve_purpose_infers_long_easy() -> None:
    """120 min at an easy class with no prescription reads as an aerobic long run."""
    resolved = resolve_purpose(None, {"moving_minutes": 120, "intensity_class": 1})
    assert resolved.id == "long_easy"
    assert resolved.source == "inferred"


def test_resolve_purpose_infers_long_goal_pace() -> None:
    """120 min at a tempo class reads as a goal-pace long run."""
    resolved = resolve_purpose(None, {"moving_minutes": 120, "intensity_class": 2})
    assert resolved.id == "long_goal_pace"
    assert resolved.source == "inferred"


def test_resolve_purpose_infers_race_by_goal_date() -> None:
    """A run on the goal race date is the race, whatever else it looks like."""
    resolved = resolve_purpose(
        None,
        {"is_goal_race_day": True, "moving_minutes": 240, "has_rep_structure": True},
    )
    assert resolved.id == "race"
    assert resolved.source == "inferred"


def test_resolve_purpose_infers_intervals_from_reps() -> None:
    """A repeat structure reads as intervals."""
    resolved = resolve_purpose(None, {"has_rep_structure": True, "moving_minutes": 50})
    assert resolved.id == "intervals"
    assert resolved.source == "inferred"


def test_resolve_purpose_unknown_default() -> None:
    """No prescription and no facts leave the purpose unknown."""
    resolved = resolve_purpose(None, {})
    assert resolved.id == "unknown"
    assert resolved.source == "default"


def test_resolve_purpose_infers_race_by_name() -> None:
    """A race-marked activity name reads as a race."""
    assert resolve_purpose(None, {"activity_name": "新潟シティマラソン"}).id == "race"


def test_resolve_purpose_rest_row_falls_back_to_inference() -> None:
    """A run on a rest day has no session default, so the data decides."""
    resolved = resolve_purpose(
        {"session_type": "rest"}, {"moving_minutes": 40, "intensity_class": 1}
    )
    assert resolved.id == "easy"
    assert resolved.source == "inferred"


def test_session_defaults_are_compatible() -> None:
    """Every session default is a purpose declarable on that session type."""
    for session_type, purpose_id in DEFAULT_PURPOSE_BY_SESSION.items():
        assert session_type in PURPOSES[purpose_id].session_types
