"""API tests for GET /api/race-readiness (#362) and /api/race-prediction-history
(#1133)."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_race_readiness_endpoint_shape(race_readiness_db_path):
    client = TestClient(create_app(db_path=race_readiness_db_path))
    response = client.get("/api/race-readiness")

    assert response.status_code == 200
    payload = response.json()

    # Top-level keys present.
    assert set(payload) >= {"current_vdot", "predicted_times", "goal", "progress"}

    # VDOT computed from the vo2_max fixture row.
    assert isinstance(payload["current_vdot"], (int, float))
    assert payload["current_vdot"] > 0

    # Predictions cover the four standard distances, all positive seconds.
    predicted = payload["predicted_times"]
    assert set(predicted) == {"race_5k", "race_10k", "half", "full"}
    assert all(isinstance(v, int) and v > 0 for v in predicted.values())

    # Active goal echoed back.
    goal = payload["goal"]
    assert goal is not None
    assert goal["race_name"] == "さいたまマラソン"
    assert goal["target_time_seconds"] == 16200

    # Progress block compares prediction vs target.
    progress = payload["progress"]
    assert progress is not None
    assert isinstance(progress["predicted_time_seconds"], int)
    assert isinstance(progress["gap_seconds"], int)
    assert progress["status"] in {"ahead", "on_track", "behind"}


@pytest.mark.integration
def test_race_readiness_no_goal(race_readiness_no_goal_db_path):
    client = TestClient(create_app(db_path=race_readiness_no_goal_db_path))
    response = client.get("/api/race-readiness")

    assert response.status_code == 200
    payload = response.json()

    # No goal row -> goal and progress are null.
    assert payload["goal"] is None
    assert payload["progress"] is None

    # VDOT is still computed, so predictions stay non-empty.
    assert payload["current_vdot"] is not None
    assert payload["predicted_times"] != {}


@pytest.mark.integration
def test_api_race_prediction_history_shape(race_readiness_db_path):
    client = TestClient(create_app(db_path=race_readiness_db_path))
    response = client.get("/api/race-prediction-history")

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) == {"goal", "source", "series"}
    assert payload["goal"]["race_name"] == "さいたまマラソン"
    # The fixture has no laps, so the curve is empty and Garmin's VO2max row
    # (52.0) carries the single plotted point.
    assert payload["source"] == "garmin_vo2max"

    series = payload["series"]
    assert len(series) >= 1
    assert set(series[0]) == {
        "date",
        "vdot",
        "predicted_time_seconds",
        "gap_seconds",
    }
    assert series[0]["gap_seconds"] == series[0]["predicted_time_seconds"] - 16200


@pytest.mark.integration
def test_api_race_prediction_history_no_goal(race_readiness_no_goal_db_path):
    client = TestClient(create_app(db_path=race_readiness_no_goal_db_path))
    response = client.get("/api/race-prediction-history")

    assert response.status_code == 200
    payload = response.json()

    # No goal row -> nothing to predict against.
    assert payload["goal"] is None
    assert payload["source"] is None
    assert payload["series"] == []
