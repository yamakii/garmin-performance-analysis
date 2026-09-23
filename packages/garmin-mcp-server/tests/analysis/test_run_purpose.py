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


def test_resolve_purpose_race_name_needs_race_effort() -> None:
    """A race-like name is a race only at a race effort (#1322).

    Garmin's coached pre-race tune-up and a fun run beside a child carry the
    fragments at an easy effort; a marathon run hard is the race.
    """
    for name in ("レース前ワークアウト", "親子マラソン"):
        resolved = resolve_purpose(
            None,
            {"activity_name": name, "moving_minutes": 30, "intensity_class": 1},
        )
        assert resolved.id == "easy", name
    resolved = resolve_purpose(
        None,
        {"activity_name": "東京マラソン", "moving_minutes": 200, "intensity_class": 2},
    )
    assert resolved.id == "race"
    assert resolved.source == "inferred"


def test_resolve_purpose_infers_recovery_from_training_type() -> None:
    """Garmin's raw ``recovery`` label reads as a recovery run (#1322).

    The canonical intensity category folds recovery into easy, so only the
    raw training type tells them apart.
    """
    resolved = resolve_purpose(
        None,
        {
            "moving_minutes": 30,
            "intensity_class": 1,
            "intensity_category": "easy",
            "training_type": "recovery",
        },
    )
    assert resolved.id == "recovery"
    assert resolved.source == "inferred"


def test_resolve_purpose_prescribed_race_day_uses_session_default() -> None:
    """With a prescription the calendar does not override it (#1352).

    The race is declared on the row; a row that does not declare it is read
    as its session type, not inferred into a race.
    """
    resolved = resolve_purpose(
        {"session_type": "long", "purpose": None},
        {"is_goal_race_day": True, "moving_minutes": 240},
    )
    assert resolved.id == "long_easy"
    assert resolved.source == "session_default"


def test_resolve_purpose_prescribed_race_declared() -> None:
    """A race day declared on the prescription is the race, from the plan."""
    resolved = resolve_purpose(
        {"session_type": "long", "purpose": "race"},
        {"is_goal_race_day": True, "moving_minutes": 240},
    )
    assert resolved.id == "race"
    assert resolved.source == "prescription"


def test_resolve_purpose_unprescribed_race_day_inferred() -> None:
    """Without a prescription the goal race's day is still inferred as race."""
    resolved = resolve_purpose(
        None,
        {"is_goal_race_day": True, "moving_minutes": 240},
    )
    assert resolved.id == "race"
    assert resolved.source == "inferred"


def test_resolve_purpose_marked_progression_overrides_session_default() -> None:
    """A build-up the prescription names and the run shows is a progression."""
    resolved = resolve_purpose(
        {"session_type": "tempo", "purpose": None},
        {"is_marked_progression": True, "is_progression": True},
    )
    assert resolved.id == "progression"
    assert resolved.source == "prescription"


def test_resolve_purpose_unmarked_progression_keeps_session_default() -> None:
    """A progression read off the data alone never overrides the plan.

    HR drift with a quick last km on an easy long run looks like a build-up;
    turning it into one would make the run's walk breaks concerns.
    """
    resolved = resolve_purpose(
        {"session_type": "long", "purpose": None},
        {"is_progression": True, "is_marked_progression": False},
    )
    assert resolved.id == "long_easy"
    assert resolved.source == "session_default"


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
