"""Counterweight facts beside a fired conservative gate (Issue #1571)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.gate_counterweight import build_counterweight


def _standing(
    steps: list[dict[str, Any]],
    weeks_to_race: int | None = 5,
    goals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    default_goals = [
        {
            "race_name": "Spring Marathon",
            "race_date": "2026-12-20",
            "priority": "A",
            "distance_km": 42.195,
            "target_time_seconds": 16200,
            "goal_pace_sec_per_km": 383.9,
            "weeks_to_race": weeks_to_race,
        }
    ]
    return {
        "on_date": "2026-11-12",
        "goals": default_goals if goals is None else goals,
        "block": None,
        "remaining_steps": steps,
        "proven": {
            "longest_run": {
                "activity_id": 1,
                "date": "2026-11-01",
                "distance_km": 24.0,
            },
            "build_baseline_km": 42.5,
        },
        "recent_near_goal_pace": [],
        "missing": [],
    }


_THREE_STEPS = [
    {"week_start": "2026-11-16", "target_km": 25.0, "kind": "build"},
    {"week_start": "2026-11-23", "target_km": 28.0, "kind": "build"},
    {"week_start": "2026-11-30", "target_km": 30.0, "kind": "build"},
]


@pytest.mark.unit
def test_counterweight_lists_remaining_steps() -> None:
    result = build_counterweight(_standing(_THREE_STEPS), ["acwr"])

    demand = result["goal_demand"]
    assert demand["longest_remaining_km"] == 30
    assert demand["weeks_to_race"] == 5
    assert demand["race_name"] == "Spring Marathon"
    assert [s["target_km"] for s in demand["remaining_steps"]] == [25.0, 28.0, 30.0]
    assert result["proven"] == {
        "longest_run": {"activity_id": 1, "date": "2026-11-01", "distance_km": 24.0},
        "build_baseline_km": 42.5,
    }
    assert result["fired"] == ["acwr"]


@pytest.mark.unit
def test_hold_cost_counts_shifted_steps() -> None:
    # 5 weeks to race, 3 build steps -> 1 week of slack -> 2 steps move back.
    result = build_counterweight(_standing(_THREE_STEPS), ["cutback_long_run"])

    assert "2段" in result["hold_cost_ja"]
    assert "空き週は1週" in result["hold_cost_ja"]


@pytest.mark.unit
def test_hold_cost_absorbed_by_slack() -> None:
    # 8 weeks to race, 3 build steps -> 4 weeks of slack -> nothing moves back.
    result = build_counterweight(_standing(_THREE_STEPS, weeks_to_race=8), ["acwr"])

    assert "後ろへずれる段はありません" in result["hold_cost_ja"]


@pytest.mark.unit
def test_counterweight_without_goal() -> None:
    result = build_counterweight(_standing(_THREE_STEPS, goals=[]), ["event_window"])

    assert result["goal_demand"] is None
    assert "登録されていない" in result["hold_cost_ja"]
    assert result["proven"]["build_baseline_km"] == 42.5


@pytest.mark.unit
def test_no_counterweight_when_nothing_fired() -> None:
    assert build_counterweight(_standing(_THREE_STEPS), []) == {}
