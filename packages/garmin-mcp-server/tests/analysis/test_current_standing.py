"""Unit tests for ``build_current_standing`` (Issue #1569)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.current_standing import (
    MISSING_NO_ACTIVE_GOAL,
    MISSING_NO_BLOCK,
    build_current_standing,
)

_BASELINE_OK = {"status": "ok", "weekly_km": 55.0}


def _standing(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "on_date": "2026-01-01",
        "goals": [],
        "blocks": [],
        "proven_long_run": None,
        "build_baseline": _BASELINE_OK,
        "recent_runs": [],
    }
    kwargs.update(overrides)
    return build_current_standing(**kwargs)


def _goal(**overrides: Any) -> dict[str, Any]:
    goal: dict[str, Any] = {
        "race_name": "Half",
        "race_date": "2026-02-12",
        "priority": "A",
        "distance_km": 21.0975,
        "target_time_seconds": 7560,
        "status": "active",
    }
    goal.update(overrides)
    return goal


@pytest.mark.unit
def test_goal_pace_from_target_time() -> None:
    result = _standing(goals=[_goal()])
    assert result["goals"][0]["goal_pace_sec_per_km"] == pytest.approx(358.3, abs=0.1)


@pytest.mark.unit
def test_goal_without_target_has_no_pace() -> None:
    result = _standing(goals=[_goal(target_time_seconds=None)])
    assert result["goals"][0]["goal_pace_sec_per_km"] is None


@pytest.mark.unit
def test_weeks_to_race() -> None:
    result = _standing(on_date="2026-01-01", goals=[_goal(race_date="2026-02-12")])
    assert result["goals"][0]["weeks_to_race"] == 6


@pytest.mark.unit
def test_block_and_steps_for_date() -> None:
    block = {
        "phase": "build",
        "title": "Half build",
        "purpose": "extend the long run",
        "start_date": "2025-12-22",
        "end_date": "2026-01-18",
        "long_run_ladder": [
            {"week_start": "2025-12-22", "target_km": 14.0, "kind": "build"},
            {"week_start": "2025-12-29", "target_km": 16.0, "kind": "build"},
            {"week_start": "2026-01-05", "target_km": 12.0, "kind": "cutback"},
            {"week_start": "2026-01-12", "target_km": 18.0, "kind": "build"},
        ],
    }
    result = _standing(on_date="2026-01-01", goals=[_goal()], blocks=[block])

    view = result["block"]
    assert view["phase"] == "build"
    assert view["title"] == "Half build"
    assert view["week_position"] == {"week": 2, "of": 4}
    assert view["current_step"] == {
        "week_start": "2025-12-29",
        "target_km": 16.0,
        "kind": "build",
    }
    assert view["next_step"]["week_start"] == "2026-01-05"
    assert [s["week_start"] for s in result["remaining_steps"]] == [
        "2026-01-05",
        "2026-01-12",
    ]
    assert MISSING_NO_BLOCK not in result["missing"]


@pytest.mark.unit
def test_recent_near_goal_pace_filters() -> None:
    goal = _goal(distance_km=10.0, target_time_seconds=3580, race_name="10k")
    runs = [
        {
            "date": "2025-12-20",
            "distance_km": 10.0,
            "avg_pace_sec_per_km": 360.0,
            "avg_hr": 160,
            "training_type": "tempo",
        },
        {
            "date": "2025-12-22",
            "distance_km": 10.0,
            "avg_pace_sec_per_km": 400.0,
            "avg_hr": 140,
            "training_type": "aerobic_base",
        },
        {
            "date": "2025-12-24",
            "distance_km": 3.0,
            "avg_pace_sec_per_km": 358.0,
            "avg_hr": 158,
            "training_type": "tempo",
        },
    ]
    result = _standing(goals=[goal], recent_runs=runs)

    near = result["recent_near_goal_pace"]
    assert len(near) == 1
    assert near[0]["date"] == "2025-12-20"
    assert near[0]["distance_km"] == 10.0
    assert near[0]["pace"] == 360.0
    assert near[0]["goal"] == "10k"


@pytest.mark.unit
def test_missing_lists_absent_inputs() -> None:
    result = _standing(goals=[], blocks=[])
    assert MISSING_NO_ACTIVE_GOAL in result["missing"]
    assert MISSING_NO_BLOCK in result["missing"]
    assert result["block"] is None
    assert result["remaining_steps"] == []
    assert result["goals"] == []
