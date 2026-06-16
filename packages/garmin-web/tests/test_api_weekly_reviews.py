"""API tests for the weekly-reviews endpoints."""

import json

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_api_weekly_reviews_list(weekly_reviews_db_path):
    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    # newest first
    assert payload[0]["week_start_date"] == "2026-06-15"
    assert isinstance(payload[0]["review_data"], dict)


@pytest.mark.integration
def test_api_weekly_review_detail(weekly_reviews_db_path):
    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews/2026-06-08")

    assert response.status_code == 200
    payload = response.json()
    assert payload["week_start_date"] == "2026-06-08"
    assert payload["review_data"]["periodization"]["b_race"] == "新潟シティマラソン"


@pytest.mark.integration
def test_api_weekly_review_detail_404(weekly_reviews_db_path):
    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews/2099-01-01")

    assert response.status_code == 404


@pytest.mark.integration
def test_get_weekly_review_versions_endpoint(weekly_reviews_db_path):
    # Append 2 more versions for 2026-06-08 (fixture has 1) with distinct
    # created_at so the week has 3 versions, newest first.
    conn = duckdb.connect(str(weekly_reviews_db_path))
    try:
        for review_id, created_at, marker in [
            (401, "2026-06-16 10:00:00", "v2"),
            (402, "2099-01-01 00:00:00", "v3"),
        ]:
            conn.execute(
                "INSERT INTO weekly_reviews ("
                "review_id, user_id, week_start_date, week_end_date,"
                " review_date, review_data, created_at, agent_name,"
                " agent_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    review_id,
                    "default",
                    "2026-06-08",
                    "2026-06-14",
                    "2026-06-15",
                    json.dumps({"marker": marker}, ensure_ascii=False),
                    created_at,
                    "weekly-review",
                    "1.0",
                ],
            )
    finally:
        conn.close()

    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews/2026-06-08/versions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    # newest first
    created = [v["created_at"] for v in payload]
    assert created == sorted(created, reverse=True)
    assert payload[0]["review_id"] == 402
    assert isinstance(payload[0]["review_data"], dict)


@pytest.mark.integration
def test_get_weekly_review_versions_empty(weekly_reviews_db_path):
    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews/2099-12-31/versions")

    assert response.status_code == 200
    assert response.json() == []
