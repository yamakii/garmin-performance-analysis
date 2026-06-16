"""Integration tests for the athlete profile inserter + reader roundtrip.

Uses the module-scoped ``initialized_db_path`` fixture (schema pre-initialized
via file copy) to avoid per-test GarminDBWriter DDL overhead.
"""

import pytest

from garmin_mcp.database.inserters.athlete import (
    insert_athlete_profile,
    insert_weekly_review,
)
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


def _weekly_review(
    week_start_date: str = "2026-06-08", volume_km: float = 28.8
) -> dict:
    return {
        "user_id": "default",
        "week_start_date": week_start_date,
        "week_end_date": "2026-06-14",
        "review_date": "2026-06-14",
        "review_data": {
            "this_week": {"volume_km": volume_km, "run_count": 4},
            "garmin_next_week": [
                {"date": "2026-06-16", "title": "Tempo", "type": "fbtAdaptiveWorkout"}
            ],
            "verdict": [
                {
                    "date": "2026-06-20",
                    "session": "Anaerobic",
                    "rating": "🔴",
                    "comment": "強度過多に注意",
                }
            ],
            "recommendations": ["Z2を維持する"],
            "overall": "順調に積み上げ",
        },
        "agent_name": "weekly-review",
        "agent_version": "1.0",
    }


@pytest.mark.integration
def test_save_then_get_weekly_review(initialized_db_path) -> None:
    """Save a weekly review, then get it back with review_data JSON restored."""
    db_path = str(initialized_db_path)
    review = _weekly_review()
    assert insert_weekly_review(review, db_path=db_path) is True

    result = AthleteReader(db_path=db_path).get_weekly_review()

    assert result is not None
    assert result["user_id"] == "default"
    assert result["week_start_date"] == "2026-06-08"
    assert result["week_end_date"] == "2026-06-14"
    assert result["review_date"] == "2026-06-14"
    assert result["agent_name"] == "weekly-review"
    assert result["agent_version"] == "1.0"
    assert result["review_data"] == review["review_data"]
    assert result["review_data"]["this_week"]["volume_km"] == 28.8
    assert result["review_data"]["verdict"][0]["rating"] == "🔴"


def _set_review_created_at(db_path: str, review_id: int, created_at: str) -> None:
    """Force a specific created_at on a row for deterministic version ordering.

    The production DEFAULT (CURRENT_TIMESTAMP) can tie within the same second,
    so version-ordering assertions set distinct created_at values explicitly.
    """
    from garmin_mcp.database.connection import get_write_connection

    with get_write_connection(db_path) as conn:
        conn.execute(
            "UPDATE weekly_reviews SET created_at = ? WHERE review_id = ?",
            [created_at, review_id],
        )


def _latest_review_id(db_path: str) -> int:
    from garmin_mcp.database.connection import get_connection

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT review_id FROM weekly_reviews "
            "ORDER BY review_id DESC LIMIT 1"
        ).fetchone()
    return int(row[0])


@pytest.mark.integration
def test_insert_weekly_review_appends_new_version(initialized_db_path) -> None:
    """Saving the same week twice appends a new version (2 rows, distinct ids)."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(volume_km=28.8), db_path=db_path)
    insert_weekly_review(_weekly_review(volume_km=35.5), db_path=db_path)

    versions = AthleteReader(db_path=db_path).list_weekly_review_versions("2026-06-08")
    assert len(versions) == 2
    review_ids = {v["review_id"] for v in versions}
    assert len(review_ids) == 2
    volumes = {v["review_data"]["this_week"]["volume_km"] for v in versions}
    assert volumes == {28.8, 35.5}


@pytest.mark.integration
def test_insert_weekly_review_distinct_weeks(initialized_db_path) -> None:
    """Saving two distinct weeks yields two rows (regression)."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(week_start_date="2026-06-01"), db_path=db_path)
    insert_weekly_review(_weekly_review(week_start_date="2026-06-08"), db_path=db_path)

    reviews = AthleteReader(db_path=db_path).list_weekly_reviews()
    assert len(reviews) == 2
    weeks = {r["week_start_date"] for r in reviews}
    assert weeks == {"2026-06-01", "2026-06-08"}


@pytest.mark.integration
def test_get_weekly_review_returns_latest_version(initialized_db_path) -> None:
    """get_weekly_review(week) returns the latest version (highest created_at)."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(volume_km=28.8), db_path=db_path)
    first_id = _latest_review_id(db_path)
    _set_review_created_at(db_path, first_id, "2026-06-14 09:00:00")

    insert_weekly_review(_weekly_review(volume_km=35.5), db_path=db_path)
    second_id = _latest_review_id(db_path)
    _set_review_created_at(db_path, second_id, "2026-06-14 18:00:00")

    result = AthleteReader(db_path=db_path).get_weekly_review("2026-06-08")
    assert result is not None
    assert result["review_id"] == second_id
    assert result["review_data"]["this_week"]["volume_km"] == 35.5


@pytest.mark.integration
def test_get_weekly_review_none_returns_latest_week_latest_version(
    initialized_db_path,
) -> None:
    """get_weekly_review(None) returns the latest version of the most recent week."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(week_start_date="2026-06-01"), db_path=db_path)

    insert_weekly_review(
        _weekly_review(week_start_date="2026-06-08", volume_km=28.8), db_path=db_path
    )
    older_id = _latest_review_id(db_path)
    _set_review_created_at(db_path, older_id, "2026-06-14 09:00:00")

    insert_weekly_review(
        _weekly_review(week_start_date="2026-06-08", volume_km=35.5), db_path=db_path
    )
    newer_id = _latest_review_id(db_path)
    _set_review_created_at(db_path, newer_id, "2026-06-14 18:00:00")

    result = AthleteReader(db_path=db_path).get_weekly_review()
    assert result is not None
    assert result["week_start_date"] == "2026-06-08"
    assert result["review_id"] == newer_id
    assert result["review_data"]["this_week"]["volume_km"] == 35.5


@pytest.mark.integration
def test_list_weekly_reviews_dedupes_per_week(initialized_db_path) -> None:
    """list_weekly_reviews returns one (latest) row per week despite versions."""
    db_path = str(initialized_db_path)
    # Two versions of the same week + one distinct week.
    insert_weekly_review(
        _weekly_review(week_start_date="2026-06-08", volume_km=28.8), db_path=db_path
    )
    insert_weekly_review(
        _weekly_review(week_start_date="2026-06-08", volume_km=35.5), db_path=db_path
    )
    insert_weekly_review(_weekly_review(week_start_date="2026-06-01"), db_path=db_path)

    reviews = AthleteReader(db_path=db_path).list_weekly_reviews()
    assert len(reviews) == 2
    weeks = {r["week_start_date"] for r in reviews}
    assert weeks == {"2026-06-08", "2026-06-01"}


@pytest.mark.integration
def test_list_weekly_review_versions_returns_all(initialized_db_path) -> None:
    """list_weekly_review_versions returns all 3 versions, created_at DESC."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(volume_km=10.0), db_path=db_path)
    _set_review_created_at(db_path, _latest_review_id(db_path), "2026-06-14 09:00:00")
    insert_weekly_review(_weekly_review(volume_km=20.0), db_path=db_path)
    _set_review_created_at(db_path, _latest_review_id(db_path), "2026-06-14 12:00:00")
    insert_weekly_review(_weekly_review(volume_km=30.0), db_path=db_path)
    _set_review_created_at(db_path, _latest_review_id(db_path), "2026-06-14 18:00:00")

    versions = AthleteReader(db_path=db_path).list_weekly_review_versions("2026-06-08")
    assert len(versions) == 3
    ordered_volumes = [
        v["review_data"]["this_week"]["volume_km"] for v in versions
    ]
    assert ordered_volumes == [30.0, 20.0, 10.0]


@pytest.mark.integration
def test_list_weekly_review_versions_empty(initialized_db_path) -> None:
    """list_weekly_review_versions returns [] when no review exists for the week."""
    db_path = str(initialized_db_path)
    insert_weekly_review(_weekly_review(week_start_date="2026-06-08"), db_path=db_path)

    versions = AthleteReader(db_path=db_path).list_weekly_review_versions("2099-01-04")
    assert versions == []
