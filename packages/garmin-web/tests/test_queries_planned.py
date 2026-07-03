"""Tests for garmin_web.queries.planned + the /planned-workouts/today route."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from garmin_mcp.database.connection import get_connection

from garmin_web.app import create_app
from garmin_web.queries.planned import get_planned_workout_for_date


@pytest.mark.unit
def test_planned_workout_for_date_found(planned_workouts_db_path: Any) -> None:
    """A planned tempo on 2026-07-02 returns its latest-version dict."""
    with get_connection(planned_workouts_db_path) as conn:
        workout = get_planned_workout_for_date(conn, "2026-07-02")

    assert workout is not None
    # Latest version wins (v2 over v1).
    assert workout["workout_id"] == "w-0702-v2"
    assert workout["workout_type"] == "tempo"
    assert workout["description_ja"] == "テンポ走 6km"
    assert workout["target_distance_km"] == 6.0
    assert workout["target_pace_low"] == 305.0
    assert workout["target_pace_high"] == 315.0
    assert workout["target_hr_low"] == 152
    assert workout["target_hr_high"] == 163


@pytest.mark.unit
def test_planned_workout_for_date_none(planned_workouts_db_path: Any) -> None:
    """A day with no planned workout returns None (API surfaces 200 + null)."""
    with get_connection(planned_workouts_db_path) as conn:
        workout = get_planned_workout_for_date(conn, "2099-01-01")
    assert workout is None

    client = TestClient(create_app(db_path=planned_workouts_db_path))
    response = client.get("/api/planned-workouts/today?date=2099-01-01")
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.unit
def test_planned_workout_today_endpoint_returns_row(
    planned_workouts_db_path: Any,
) -> None:
    """The API returns the planned row for an explicit date param."""
    client = TestClient(create_app(db_path=planned_workouts_db_path))
    response = client.get("/api/planned-workouts/today?date=2026-07-03")
    assert response.status_code == 200
    payload = response.json()
    assert payload is not None
    assert payload["workout_type"] == "easy"
    assert payload["target_distance_km"] == 8.0
