"""API tests for the weekly-reviews endpoints."""

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
