"""API tests for activity detail endpoints."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

FULL_ACTIVITY_ID = 9000000101  # 2000 time-series rows with GPS
PARTIAL_ACTIVITY_ID = 9000000102  # 300 time-series rows, no GPS (indoor)


@pytest.mark.integration
def test_api_detail_endpoints_200(detail_db_path):
    client = TestClient(create_app(db_path=detail_db_path))

    # Detail endpoint
    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["activity"]["activity_id"] == FULL_ACTIVITY_ID
    assert len(detail["splits"]) == 5
    assert detail["form_efficiency"] is not None
    assert len(detail["hr_zones"]) == 5

    # Time-series endpoint (metrics required)
    response = client.get(
        f"/api/activities/{FULL_ACTIVITY_ID}/time-series",
        params={"metrics": "heart_rate,speed", "max_points": 500},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["timestamps"]) <= 500
    assert set(payload["metrics"].keys()) == {"heart_rate", "speed"}

    # Time-series without metrics -> 422
    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}/time-series")
    assert response.status_code == 422

    # Time-series with unknown metric -> 422
    response = client.get(
        f"/api/activities/{FULL_ACTIVITY_ID}/time-series",
        params={"metrics": "bogus"},
    )
    assert response.status_code == 422

    # Sections endpoint
    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}/sections")
    assert response.status_code == 200
    sections = response.json()
    assert set(sections.keys()) == {
        "split",
        "phase",
        "efficiency",
        "environment",
        "summary",
    }
    assert all(s["parse_error"] is False for s in sections.values())


@pytest.mark.integration
def test_api_track_200(detail_db_path):
    client = TestClient(create_app(db_path=detail_db_path))
    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}/track")

    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) == 2000
    assert points[0] == {"seq_no": 0, "lat": 35.6, "lon": 139.7}
    assert [p["seq_no"] for p in points] == sorted(p["seq_no"] for p in points)


@pytest.mark.integration
def test_api_track_empty_for_indoor(detail_db_path):
    client = TestClient(create_app(db_path=detail_db_path))
    response = client.get(f"/api/activities/{PARTIAL_ACTIVITY_ID}/track")

    assert response.status_code == 200
    assert response.json()["points"] == []


@pytest.mark.integration
def test_api_detail_404(detail_db_path):
    client = TestClient(create_app(db_path=detail_db_path))
    response = client.get("/api/activities/999999")

    assert response.status_code == 404
