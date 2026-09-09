"""prefetch_weekly_review_context end to end against a seeded DuckDB (read-only, derived verdict)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _weeks_to_race,
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import (
    _insert_activity,
    _no_network,
    _row_count,
    _seed_profile_and_goal,
)


@pytest.mark.integration
def test_prefetch_weekly_review_context_end_to_end(db_path: Path) -> None:
    """A seeded W-1/W -> all keys present, both windows resolved, serializable."""
    # W = 2026-07-06..07-12 (this week for today=07-10); W-1 = 06-29..07-05.
    _insert_activity(db_path, 849000001, "2026-07-01")  # prev week
    _insert_activity(db_path, 849000002, "2026-07-08")  # current week
    _seed_profile_and_goal(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    json.dumps(result, default=str)  # MCP-boundary serializable

    for key in (
        "week_start_date",
        "week_end_date",
        "prev_start",
        "prev_end",
        "week_in_progress",
        "week_start_day",
        "as_of",
        "activity_ids",
        "activities",
        "fitness_summary",
        "load_trend",
        "acwr",
        "recovery",
        "strength",
        "hiking",
        "training_block",
        "prescriptions_prev_week",
        "prescriptions_current_week",
        "scheduled_workouts",
        "garmin_conflicts",
        "athlete_profile",
        "goals_with_weeks_to_race",
        "past_review",
    ):
        assert key in result

    # Plan backbone against an empty ledger: shapes are present, values empty.
    assert result["training_block"]["block"] is None
    assert result["prescriptions_prev_week"]["adherence"]["prescribed"] == 0
    assert result["garmin_conflicts"] == []

    assert result["activity_ids"]["prev_week"] == [849000001]
    assert result["activity_ids"]["current_week"] == [849000002]
    assert {a["activity_id"] for a in result["activities"]} == {849000001, 849000002}

    # recovery is a nested triple of collectors.
    assert set(result["recovery"]) == {"trend", "status", "baseline_deviation"}

    # goals_with_weeks_to_race carries the pre-computed ceiling, and is the
    # bundle's only copy of the goals (Issue #933).
    goals = result["goals_with_weeks_to_race"]
    assert len(goals) == 1
    assert goals[0]["weeks_to_race"] == _weeks_to_race("2026-10-11", date(2026, 7, 6))
    assert "goals" not in result["athlete_profile"]


@pytest.mark.unit
def test_past_review_verdict_is_derived(db_path: Path) -> None:
    """The past review's verdict comes from its prescription batch (#1021)."""
    from garmin_mcp.database.inserters.athlete import insert_weekly_review
    from garmin_mcp.database.inserters.plan import insert_weekly_prescriptions

    _seed_profile_and_goal(db_path)
    review_id = int(
        insert_weekly_review(
            {
                "week_start_date": "2026-07-06",
                "week_end_date": "2026-07-12",
                "review_date": "2026-07-10",
                "review_data": {"overall": "順調"},
            },
            db_path=str(db_path),
        )
    )
    saved = insert_weekly_prescriptions(
        "2026-07-06",
        [
            {
                "date": "2026-07-12",
                "session_type": "long",
                "title": "ロング 22km",
                "target_km": 22.0,
                "rating": "✅",
                "rationale": "ラダー2段目",
            }
        ],
        review_id=review_id,
        db_path=str(db_path),
    )

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    review_data = result["past_review"]["review_data"]
    assert review_data["verdict_source"] == "prescriptions"
    assert review_data["prescription_batch_id"] == saved["batch_id"]
    assert review_data["verdict"][0]["session"] == "ロング 22km"
    assert review_data["verdict"][0]["rating"] == "✅"

    current = result["prescriptions_current_week"]
    assert current["review_id"] == review_id
    assert current["batch_id"] == saved["batch_id"]
    assert [row["title"] for row in current["rows"]] == ["ロング 22km"]


@pytest.mark.integration
def test_prefetch_is_read_only(db_path: Path) -> None:
    """Collection writes nothing (catch_up_ingest is intentionally excluded)."""
    _insert_activity(db_path, 849000010, "2026-07-01")
    before = _row_count(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    assert _row_count(db_path) == before
