"""API tests for GET /api/trends/*."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_ENDPOINTS = (
    "/api/trends/volume",
    "/api/trends/physiology",
    "/api/trends/form",
    "/api/trends/efficiency",
)


@pytest.mark.integration
def test_api_trends_all_endpoints_200(trends_db_path, empty_trends_db_path):
    client = TestClient(create_app(db_path=trends_db_path))
    for endpoint in _ENDPOINTS:
        response = client.get(endpoint)
        assert response.status_code == 200, endpoint

    volume = client.get("/api/trends/volume", params={"granularity": "month"})
    assert volume.status_code == 200
    assert [bucket["bucket"] for bucket in volume.json()] == ["2025-10", "2025-11"]

    # Weekly buckets key on the week's start date (Monday by default, since the
    # trends fixture has no athlete_profile row -> week_start_day falls back to 0)
    weekly = client.get("/api/trends/volume", params={"granularity": "week"})
    assert weekly.status_code == 200
    assert [bucket["bucket"] for bucket in weekly.json()] == [
        "2025-10-06",
        "2025-10-13",
        "2025-11-03",
    ]

    # Invalid granularity is rejected by FastAPI validation
    invalid = client.get("/api/trends/volume", params={"granularity": "day"})
    assert invalid.status_code == 422

    # Empty DB returns 200 with empty payloads
    empty_client = TestClient(create_app(db_path=empty_trends_db_path))
    assert empty_client.get("/api/trends/volume").json() == []
    assert empty_client.get("/api/trends/form").json() == []
    assert empty_client.get("/api/trends/efficiency").json() == []
    physiology = empty_client.get("/api/trends/physiology")
    assert physiology.status_code == 200
    assert physiology.json() == {"vo2max": [], "lactate_threshold": []}


@pytest.mark.integration
def test_api_heat_adjusted_returns_payload(heat_db_path):
    client = TestClient(create_app(db_path=heat_db_path))

    response = client.get("/api/trends/heat-adjusted", params={"days": 365})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "coefficients" in body
    assert "points" in body
    assert len(body["points"]) >= 10


@pytest.mark.integration
def test_objective_fitness_route_200(
    objective_fitness_db_path, empty_objective_fitness_db_path
):
    client = TestClient(create_app(db_path=objective_fitness_db_path))

    response = client.get("/api/trends/objective-fitness")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"objective_curve", "garmin_vo2max", "optimism_gap"}
    assert body["objective_curve"], "expected a non-empty objective curve"
    assert body["garmin_vo2max"]
    for point in body["objective_curve"]:
        assert set(point) == {"date", "vdot", "source_distance_km"}
    gap = body["optimism_gap"]
    assert set(gap) == {
        "garmin_vdot",
        "objective_vdot",
        "gap_vdot",
        "gap_pace_sec_per_km",
    }

    # Empty DB returns 200 with empty series and a null gap.
    empty_client = TestClient(create_app(db_path=empty_objective_fitness_db_path))
    empty = empty_client.get("/api/trends/objective-fitness")
    assert empty.status_code == 200
    assert empty.json() == {
        "objective_curve": [],
        "garmin_vo2max": [],
        "optimism_gap": None,
    }


@pytest.mark.integration
def test_api_heat_adjusted_rejects_bad_days(heat_db_path):
    client = TestClient(create_app(db_path=heat_db_path))

    # days below the ge=30 bound is rejected by FastAPI validation.
    response = client.get("/api/trends/heat-adjusted", params={"days": 10})

    assert response.status_code == 422
