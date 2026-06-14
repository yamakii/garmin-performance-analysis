"""Integration tests for garmin_web.queries.weekly_reviews."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.weekly_reviews import get_weekly_review, list_weekly_reviews


@pytest.mark.integration
def test_list_weekly_reviews_desc(weekly_reviews_db_path):
    with get_connection(weekly_reviews_db_path) as conn:
        reviews = list_weekly_reviews(conn)

    # 3 weeks inserted, newest first (week_start_date DESC)
    assert len(reviews) == 3
    starts = [r["week_start_date"] for r in reviews]
    assert starts == ["2026-06-15", "2026-06-08", "2026-06-01"]
    # date/timestamp values are str
    assert isinstance(reviews[0]["week_start_date"], str)
    # review_data is JSON-decoded back into a dict
    assert isinstance(reviews[0]["review_data"], dict)

    # limit is honored
    with get_connection(weekly_reviews_db_path) as conn:
        limited = list_weekly_reviews(conn, limit=2)
    assert len(limited) == 2
    assert limited[0]["week_start_date"] == "2026-06-15"
    assert limited[1]["week_start_date"] == "2026-06-08"


@pytest.mark.integration
def test_get_weekly_review_detail(weekly_reviews_db_path):
    with get_connection(weekly_reviews_db_path) as conn:
        review = get_weekly_review(conn, "2026-06-15")

    assert review is not None
    assert review["week_start_date"] == "2026-06-15"
    assert review["agent_name"] == "weekly-review"

    data = review["review_data"]
    assert isinstance(data, dict)
    # verdict restored with emoji ratings; 6/15週 has 2 red verdicts
    ratings = [v["rating"] for v in data["verdict"]]
    assert ratings.count("🔴") == 2
    # periodization (#286) restored, including null week count
    assert data["periodization"]["a_race"] == "さいたまマラソン"
    assert data["periodization"]["weeks_to_a_race"] is None
    assert data["periodization"]["weeks_to_b_race"] == 17
    # legacy keys
    assert data["this_week"]["volume_km"] == 35.5
    assert isinstance(data["recommendations"], list)


@pytest.mark.integration
def test_get_weekly_review_missing(empty_weekly_reviews_db_path):
    with get_connection(empty_weekly_reviews_db_path) as conn:
        review = get_weekly_review(conn, "2099-01-01")
    assert review is None
