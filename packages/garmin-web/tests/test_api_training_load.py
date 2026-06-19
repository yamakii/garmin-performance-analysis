"""API tests for GET /api/training-load (Issue #363)."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_training_load_endpoint_shape(training_load_db_path):
    client = TestClient(create_app(db_path=training_load_db_path))
    response = client.get("/api/training-load")

    assert response.status_code == 200
    payload = response.json()

    # Top-level keys: current snapshot + weekly trend.
    assert set(payload) == {"current", "trend"}

    # Current ACWR snapshot keys/types.
    current = payload["current"]
    assert set(current) >= {
        "acute_load_7d",
        "chronic_load_28d_weekly",
        "acwr",
        "status",
        "load_metric",
    }
    assert isinstance(current["acute_load_7d"], (int, float))
    assert isinstance(current["chronic_load_28d_weekly"], (int, float))
    assert isinstance(current["acwr"], (int, float))
    assert current["load_metric"] == "distance_km"
    # Steady ~20 km/week -> optimal range (~1.0).
    assert current["status"] == "optimal"

    # Trend has a chronological weeks array of week buckets.
    trend = payload["trend"]
    assert "weeks" in trend
    weeks = trend["weeks"]
    assert isinstance(weeks, list)
    assert len(weeks) == 12  # default lookback_weeks
    for week in weeks:
        assert set(week) >= {"week_start", "load_km", "acwr", "status"}
        assert isinstance(week["week_start"], str)
        assert isinstance(week["load_km"], (int, float))


@pytest.mark.integration
def test_training_load_high_risk(training_load_high_risk_db_path):
    client = TestClient(create_app(db_path=training_load_high_risk_db_path))
    response = client.get("/api/training-load")

    assert response.status_code == 200
    payload = response.json()

    # A recent volume spike pushes the current ACWR into the high-risk band.
    current = payload["current"]
    assert current["status"] == "high_risk"
    assert current["acwr"] > 1.5
