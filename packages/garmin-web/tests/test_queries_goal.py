"""Integration tests for garmin_web.queries.goal.get_goal."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.goal import get_goal


@pytest.mark.integration
def test_get_goal_returns_profile(goal_db_path):
    with get_connection(goal_db_path) as conn:
        result = get_goal(conn)

    profile = result["profile"]
    assert profile["current_focus"] == "サブ4達成に向けた持久力強化"
    assert profile["focus_notes"] == "週末ロング走を軸に有酸素ベースを底上げ"
    assert isinstance(profile["updated_at"], str)

    goals = result["goals"]
    assert len(goals) == 2
    assert goals[0]["race_name"] == "つくばマラソン"
    assert goals[0]["priority"] == "A"
    assert goals[0]["race_date"] == "2026-11-22"
    assert goals[0]["target_time_seconds"] == 16200
    assert goals[1]["race_name"] == "ハーフマラソン大会"
    assert goals[1]["race_date"] is None
    # date/timestamp values are str
    assert isinstance(goals[0]["race_date"], str)

    retrospectives = result["retrospectives"]
    assert len(retrospectives) == 1
    assert retrospectives[0]["season_label"] == "2025秋シーズン"
    assert retrospectives[0]["period_start"] == "2025-09-01"
    assert retrospectives[0]["key_learnings"] == "ロング走でのペース管理を重視する"


@pytest.mark.integration
def test_get_goal_empty(empty_goal_db_path):
    with get_connection(empty_goal_db_path) as conn:
        result = get_goal(conn)

    assert result["goals"] == []
    assert result["retrospectives"] == []
    assert result["profile"]["current_focus"] is None
    assert result["profile"]["focus_notes"] is None
    assert result["profile"]["updated_at"] is None
