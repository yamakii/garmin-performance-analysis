"""The weekly-review bundle carries the counterweight beside a fired gate (#1571)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _fired_gates,
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import (
    _insert_activity,
    _mock_prefetch,
    _no_network,
    _seed_profile_and_goal,
)


@pytest.mark.integration
def test_weekly_review_context_has_counterweight_when_gate_fires(
    db_path: Path,
) -> None:
    """A spike in the acute week trips the ACWR -> the goal side is surfaced.

    today = 2026-07-10: the chronic window is 06-13..07-10 and the acute week
    07-04..07-10. 10 km before the acute week and 40 km inside it give an ACWR
    of 40 / 12.5 = 3.2 (high_risk).
    """
    _insert_activity(db_path, 849100001, "2026-06-15", 10.0)
    _insert_activity(db_path, 849100002, "2026-07-05", 30.0)
    _insert_activity(db_path, 849100003, "2026-07-08", 10.0)
    _seed_profile_and_goal(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    json.dumps(result, default=str)
    assert result["acwr"]["status"] == "high_risk"

    counterweight = result["gate_counterweight"]
    assert counterweight is not None
    assert "acwr" in counterweight["fired"]
    demand = counterweight["goal_demand"]
    assert demand is not None
    assert demand["race_name"] == "Niigata"
    assert demand["weeks_to_race"] == 14
    assert counterweight["proven"]["longest_run"]["distance_km"] == 30.0
    assert counterweight["hold_cost_ja"]


@pytest.mark.unit
def test_no_counterweight_when_no_gate_fires() -> None:
    with _mock_prefetch():
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["gate_counterweight"] is None


@pytest.mark.unit
def test_fired_gates_reads_every_gate() -> None:
    load_trend = {
        "long_run": {"cutback_due_long_run": True, "cutback_due_event_window": True},
        "volume": {"consecutive_build_weeks": 3},
    }

    assert _fired_gates(load_trend, {"status": "caution"}) == [
        "acwr",
        "cutback_long_run",
        "cutback_volume",
        "event_window",
    ]
    assert _fired_gates(None, {"status": "optimal"}) == []
