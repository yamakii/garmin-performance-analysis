"""Integration tests for the athlete profile inserter + reader roundtrip.

Uses the module-scoped ``initialized_db_path`` fixture (schema pre-initialized
via file copy) to avoid per-test GarminDBWriter DDL overhead.
"""

import pytest

from garmin_mcp.database.inserters.athlete import insert_athlete_profile
from garmin_mcp.database.readers.athlete import AthleteReader


def _profile_with_two_goals() -> dict:
    return {
        "user_id": "default",
        "current_focus": "回復力と筋持久力",
        "focus_notes": "スピードは到達済み",
        "goals": [
            {
                "race_name": "さいたまマラソン",
                "race_date": "2027-02-01",
                "priority": "A",
                "goal_type": "marathon",
                "target_time_seconds": 16200,
                "status": "active",
                "notes": "サブ4.5",
            },
            {
                "race_name": "新潟シティマラソン",
                "race_date": "2026-10-11",
                "priority": "B",
                "goal_type": "marathon",
                "status": "active",
                "notes": "中間目標。ドレスリハーサル",
            },
        ],
        "retrospectives": [
            {
                "season_label": "2025-2026",
                "narrative": "ハーフ2:13後に故障",
                "key_learnings": "強い実戦直後の故障に注意",
            }
        ],
    }


@pytest.mark.integration
def test_save_then_get_profile_roundtrip(initialized_db_path) -> None:
    """Save a profile (2 goals, 1 retro), then get it back with matching values."""
    db_path = str(initialized_db_path)
    insert_athlete_profile(_profile_with_two_goals(), db_path=db_path)

    result = AthleteReader(db_path=db_path).get_athlete_profile()

    assert result["user_id"] == "default"
    assert result["current_focus"] == "回復力と筋持久力"
    assert result["focus_notes"] == "スピードは到達済み"
    assert result["updated_at"] is not None

    assert len(result["goals"]) == 2
    first = result["goals"][0]
    assert first["race_name"] == "さいたまマラソン"
    assert first["race_date"] == "2027-02-01"
    assert first["priority"] == "A"
    assert first["goal_type"] == "marathon"
    assert first["target_time_seconds"] == 16200
    assert first["status"] == "active"
    assert first["notes"] == "サブ4.5"

    second = result["goals"][1]
    assert second["race_name"] == "新潟シティマラソン"
    assert second["priority"] == "B"

    assert len(result["retrospectives"]) == 1
    retro = result["retrospectives"][0]
    assert retro["season_label"] == "2025-2026"
    assert retro["narrative"] == "ハーフ2:13後に故障"
    assert retro["key_learnings"] == "強い実戦直後の故障に注意"


@pytest.mark.integration
def test_save_profile_replaces_goals(initialized_db_path) -> None:
    """Re-saving with fewer goals fully replaces the prior set (no duplication)."""
    db_path = str(initialized_db_path)
    insert_athlete_profile(_profile_with_two_goals(), db_path=db_path)

    single_goal_profile = {
        "user_id": "default",
        "current_focus": "新フォーカス",
        "goals": [
            {
                "race_name": "東京マラソン",
                "race_date": "2027-03-01",
                "priority": "A",
                "goal_type": "marathon",
                "status": "active",
            }
        ],
        "retrospectives": [],
    }
    insert_athlete_profile(single_goal_profile, db_path=db_path)

    result = AthleteReader(db_path=db_path).get_athlete_profile()

    assert result["current_focus"] == "新フォーカス"
    assert len(result["goals"]) == 1
    assert result["goals"][0]["race_name"] == "東京マラソン"
    assert result["retrospectives"] == []


@pytest.mark.integration
def test_get_profile_empty(initialized_db_path) -> None:
    """Getting an unregistered user_id returns the empty profile structure."""
    db_path = str(initialized_db_path)

    result = AthleteReader(db_path=db_path).get_athlete_profile(user_id="ghost")

    assert result["user_id"] == "ghost"
    assert result["current_focus"] is None
    assert result["focus_notes"] is None
    assert result["updated_at"] is None
    assert result["goals"] == []
    assert result["retrospectives"] == []
