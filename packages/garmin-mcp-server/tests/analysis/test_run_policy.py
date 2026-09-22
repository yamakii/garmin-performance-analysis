"""Tests for the purpose-aware deviation policy (Issue #1314)."""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.run_policy import (
    ALWAYS_NEUTRAL_KINDS,
    POLICY,
    apply_policy,
    policy_for,
)
from garmin_mcp.analysis.run_purpose import PURPOSES

pytestmark = pytest.mark.unit


def test_policy_walk_acceptable_on_long_easy() -> None:
    """An aerobic long run tolerates walk breaks."""
    verdict, reason = policy_for("walk_break", "long_easy", None)
    assert verdict == "acceptable"
    assert "long_easy" in reason


def test_policy_walk_concern_on_long_goal_pace() -> None:
    """A goal-pace rehearsal is broken by a walk break."""
    verdict, _reason = policy_for("walk_break", "long_goal_pace", None)
    assert verdict == "concern"


def test_policy_allowance_overrides_walk() -> None:
    """``allowances.walk`` beats the table in both directions."""
    assert policy_for("walk_break", "long_goal_pace", {"walk": True})[0] == (
        "acceptable"
    )
    assert policy_for("walk_break", "long_easy", {"walk": False})[0] == "concern"
    # The allowance speaks only for walk breaks.
    assert policy_for("fade", "long_goal_pace", {"walk": True})[0] == "concern"


def test_policy_recovery_surge_neutral() -> None:
    """A quicker km on a recovery run is not a concern; HR is (#1322)."""
    assert policy_for("surge", "recovery", None)[0] == "neutral"
    # What a recovery run guards is still judged.
    assert policy_for("ceiling_touch", "recovery", None)[0] == "concern"


def test_policy_unknown_keeps_ceiling_concern() -> None:
    """``unknown`` keeps the pre-purpose behaviour: only a ceiling touch counts."""
    assert policy_for("ceiling_touch", "unknown", None)[0] == "concern"
    assert policy_for("fade", "unknown", None)[0] == "neutral"
    # A purpose id the table does not know is judged as unknown.
    assert policy_for("ceiling_touch", "not_a_purpose", None)[0] == "concern"


def test_policy_step_scenes_always_neutral() -> None:
    """Step scenes describe the session's shape, whatever the purpose."""
    assert policy_for("rep", "tempo", None)[0] == "neutral"
    for kind in ALWAYS_NEUTRAL_KINDS:
        assert policy_for(kind, "recovery", {"walk": False})[0] == "neutral"


def test_policy_table_covers_every_purpose() -> None:
    """Every purpose of the resolver has a row, so none falls back silently."""
    assert set(POLICY) == set(PURPOSES)


def test_apply_policy_returns_copies() -> None:
    """The input scenes are left untouched; the copies carry the verdict."""
    moments = [{"id": "m1", "kind": "walk_break"}, {"id": "m2", "kind": "steady"}]

    judged = apply_policy(moments, "long_goal_pace", None)

    assert "policy" not in moments[0]
    assert judged[0]["id"] == "m1"
    assert judged[0]["policy"]["verdict"] == "concern"
    assert judged[1]["policy"]["verdict"] == "neutral"
    assert set(judged[0]["policy"]) == {"verdict", "reason"}


def test_policy_breakdown_is_concern_on_long_easy() -> None:
    """A run that stopped delivering its purpose is a deviation (#1340)."""
    verdict, _reason = policy_for("breakdown", "long_easy", None)
    assert verdict == "concern"


def test_policy_breakdown_survives_a_walk_allowance() -> None:
    """Allowing walk breaks does not make the collapse acceptable."""
    verdict, _reason = policy_for("breakdown", "long_easy", {"walk": True})
    assert verdict == "concern"


def test_policy_breakdown_neutral_on_intervals() -> None:
    """Intervals are judged on their reps, not on holding one pace."""
    verdict, _reason = policy_for("breakdown", "intervals", None)
    assert verdict == "neutral"
