"""The run's average pace against each goal pace in the run-note standing (#1587).

The run-note agent transcribes numbers and never computes them, so the run pace
minus the goal pace is computed in the prefetch and carried on each goal.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.scripts.prefetch_activity_context import (
    _with_run_pace_delta,
    build_run_note_context,
)


def _standing(*paces: float | None) -> dict[str, Any]:
    return {
        "goals": [
            {"race_name": f"goal-{i}", "goal_pace_sec_per_km": pace}
            for i, pace in enumerate(paces)
        ],
        "block": None,
        "proven": {"longest_run": None, "build_baseline_km": None},
    }


@pytest.mark.unit
def test_run_pace_delta_per_goal() -> None:
    """Positive means slower than the goal pace, rounded to whole seconds."""
    out = _with_run_pace_delta(_standing(364.0, 384.0), 367.1)

    assert out is not None
    assert [g["run_avg_pace_vs_goal_s_per_km"] for g in out["goals"]] == [3, -17]


@pytest.mark.unit
def test_run_pace_delta_none_without_goal_pace() -> None:
    """A goal with no target time has no pace to compare with."""
    out = _with_run_pace_delta(_standing(None), 367.1)

    assert out is not None
    assert out["goals"][0]["run_avg_pace_vs_goal_s_per_km"] is None


@pytest.mark.unit
def test_run_pace_delta_none_without_run_pace() -> None:
    """No run pace leaves every delta None and the rest of the standing as is."""
    standing = _standing(364.0)
    out = _with_run_pace_delta(standing, None)

    assert out is not None
    assert out["goals"][0]["run_avg_pace_vs_goal_s_per_km"] is None
    assert out["goals"][0]["goal_pace_sec_per_km"] == 364.0
    assert out["proven"] == standing["proven"]


@pytest.mark.unit
def test_run_pace_delta_standing_none() -> None:
    """A failed standing read stays None."""
    assert _with_run_pace_delta(None, 367.1) is None


@pytest.mark.unit
def test_run_note_context_keeps_run_pace_delta() -> None:
    """The run-note subset of the standing keeps the delta on each goal."""
    standing = _with_run_pace_delta(_standing(364.0), 367.1)

    out = build_run_note_context({"activity_id": 1, "standing": standing})

    assert out is not None
    assert out["standing"]["goals"][0]["run_avg_pace_vs_goal_s_per_km"] == 3
