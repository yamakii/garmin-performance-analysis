"""API tests for GET /api/goal."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_api_goal_endpoint(goal_db_path):
    client = TestClient(create_app(db_path=goal_db_path))
    response = client.get("/api/goal")

    assert response.status_code == 200
    payload = response.json()

    assert payload["profile"]["current_focus"] == "サブ4達成に向けた持久力強化"
    assert len(payload["goals"]) == 2
    assert payload["goals"][0]["race_name"] == "つくばマラソン"
    assert payload["goals"][0]["target_time_seconds"] == 16200
    assert payload["goals"][1]["race_date"] is None
    assert len(payload["retrospectives"]) == 1
    assert payload["retrospectives"][0]["season_label"] == "2025秋シーズン"


@pytest.mark.integration
def test_api_goal_endpoint_empty(empty_goal_db_path):
    client = TestClient(create_app(db_path=empty_goal_db_path))
    response = client.get("/api/goal")

    assert response.status_code == 200
    payload = response.json()
    assert payload["goals"] == []
    assert payload["retrospectives"] == []
    assert payload["profile"]["current_focus"] is None
