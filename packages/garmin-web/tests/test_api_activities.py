"""API tests for GET /api/activities."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_api_activities_returns_200(fixture_db_path):
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    for item in payload:
        assert "activity_id" in item
        assert "activity_date" in item
        assert "total_distance_km" in item


@pytest.mark.unit
def test_api_activities_invalid_date_422(fixture_db_path):
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities", params={"from": "not-a-date"})

    assert response.status_code == 422
