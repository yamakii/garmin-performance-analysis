"""Integration tests for garmin_web.queries.weekly_reviews."""

import json

import duckdb
import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.weekly_reviews import (
    get_weekly_review,
    list_weekly_review_versions,
    list_weekly_reviews,
)


def _insert_version(
    db_path,
    *,
    review_id: int,
    week_start: str,
    week_end: str,
    created_at: str,
    marker: str,
) -> None:
    """Append an extra weekly_reviews version row with an explicit created_at.

    Uses a raw write connection (get_connection is read-only). Distinct
    ``created_at`` values avoid same-second ordering ties.
    """
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO weekly_reviews ("
            "review_id, user_id, week_start_date, week_end_date, review_date,"
            " review_data, created_at, agent_name, agent_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                review_id,
                "default",
                week_start,
                week_end,
                week_end,
                json.dumps({"marker": marker}, ensure_ascii=False),
                created_at,
                "weekly-review",
                "1.0",
            ],
        )
    finally:
        conn.close()


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


@pytest.mark.integration
def test_list_weekly_review_versions_returns_all(weekly_reviews_db_path):
    # Fixture already has 1 version of 2026-06-01 (review_id=1). Add 2 more
    # with distinct created_at so the week has 3 versions total.
    _insert_version(
        weekly_reviews_db_path,
        review_id=101,
        week_start="2026-06-01",
        week_end="2026-06-07",
        created_at="2026-06-08 10:00:00",
        marker="v2",
    )
    _insert_version(
        weekly_reviews_db_path,
        review_id=102,
        week_start="2026-06-01",
        week_end="2026-06-07",
        created_at="2026-06-09 10:00:00",
        marker="v3",
    )

    with get_connection(weekly_reviews_db_path) as conn:
        versions = list_weekly_review_versions(conn, "2026-06-01")

    assert len(versions) == 3
    # newest first (created_at DESC); the fixture row defaults to now() so it
    # sorts ahead of the two explicit June-08/09 timestamps.
    created = [v["created_at"] for v in versions]
    assert created == sorted(created, reverse=True)
    assert isinstance(versions[0]["review_data"], dict)


@pytest.mark.integration
def test_list_weekly_reviews_dedupes_per_week(weekly_reviews_db_path):
    # Add a 2nd version for 2026-06-08 (another week, 2026-06-01, stays single).
    _insert_version(
        weekly_reviews_db_path,
        review_id=201,
        week_start="2026-06-08",
        week_end="2026-06-14",
        created_at="2026-06-16 10:00:00",
        marker="v2",
    )

    with get_connection(weekly_reviews_db_path) as conn:
        reviews = list_weekly_reviews(conn)

    # Still one row per week (3 distinct weeks), not 4.
    starts = [r["week_start_date"] for r in reviews]
    assert starts == ["2026-06-15", "2026-06-08", "2026-06-01"]
    assert len(reviews) == 3


@pytest.mark.integration
def test_get_weekly_review_returns_latest_version(weekly_reviews_db_path):
    # Add a clearly newer version for 2026-06-08 and confirm it wins.
    _insert_version(
        weekly_reviews_db_path,
        review_id=301,
        week_start="2026-06-08",
        week_end="2026-06-14",
        created_at="2099-01-01 00:00:00",
        marker="latest",
    )

    with get_connection(weekly_reviews_db_path) as conn:
        review = get_weekly_review(conn, "2026-06-08")

    assert review is not None
    assert review["review_id"] == 301
    assert review["review_data"]["marker"] == "latest"
