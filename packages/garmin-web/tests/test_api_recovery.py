"""API tests for the recovery / body-composition endpoints (Issue #502)."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_recovery_trend_endpoint_returns_series(recovery_db_path):
    client = TestClient(create_app(db_path=recovery_db_path))
    response = client.get("/api/recovery-trend")

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) >= {"weeks", "rhr", "hrv", "series"}

    # Series is non-empty and date-ascending with the recovery markers.
    series = payload["series"]
    assert isinstance(series, list)
    assert len(series) == 5
    assert [p["date"] for p in series] == sorted(p["date"] for p in series)
    for point in series:
        assert set(point) >= {"date", "resting_hr", "hrv_overnight_ms"}

    # RHR summary block carries the 7d / 30d medians + trend classification.
    rhr = payload["rhr"]
    assert set(rhr) >= {"median_7d", "median_30d", "rhr_trend"}

    # HRV block flags the two consecutive nights below baseline as under-recovery.
    hrv = payload["hrv"]
    assert set(hrv) >= {
        "latest_ms",
        "status",
        "hrv_below_baseline_days",
        "under_recovery",
    }
    assert hrv["hrv_below_baseline_days"] == 2
    assert hrv["under_recovery"] is True


@pytest.mark.integration
def test_body_composition_trend_endpoint(body_composition_db_path):
    client = TestClient(create_app(db_path=body_composition_db_path))
    response = client.get("/api/body-composition-trend")

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) >= {"weeks", "series", "change", "lean_pwr"}

    # Series carries the weight + fat/lean decomposition, date-ascending.
    series = payload["series"]
    assert len(series) == 4
    assert [p["date"] for p in series] == sorted(p["date"] for p in series)
    for point in series:
        assert set(point) >= {"date", "weight_kg", "fat_mass", "lean_mass"}

    # The "change" key exists and reports a net weight loss over the window.
    change = payload["change"]
    assert set(change) >= {
        "delta_weight",
        "delta_fat",
        "delta_lean",
        "muscle_loss_warning",
    }
    assert change["delta_weight"] is not None
    assert change["delta_weight"] < 0

    # FTP row present -> lean power-to-weight is computed (non-null).
    assert payload["lean_pwr"] is not None


@pytest.mark.integration
def test_recovery_status_endpoint_unknown_when_empty(empty_recovery_db_path):
    client = TestClient(create_app(db_path=empty_recovery_db_path))
    response = client.get("/api/recovery-status")

    assert response.status_code == 200
    payload = response.json()

    # No daily_wellness rows -> go-by-feel unknown recommendation.
    assert payload["recommendation"] == "unknown"
    assert payload["date"] is None
