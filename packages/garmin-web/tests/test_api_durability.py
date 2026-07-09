"""API tests for GET /api/durability-trend (Issue #364)."""

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.integration
def test_durability_trend_endpoint_shape(durability_db_path):
    client = TestClient(create_app(db_path=durability_db_path))
    response = client.get(
        "/api/durability-trend",
        params={"start_date": "2025-10-01", "end_date": "2025-10-31"},
    )

    assert response.status_code == 200
    payload = response.json()

    # Top-level keys: per-activity durability + aggregate trend.
    assert set(payload) == {"activities", "trend"}

    # Two long runs (18/21 km) qualify; the 8 km run is filtered out
    # by the default min_distance_km (10 km, #695).
    activities = payload["activities"]
    assert isinstance(activities, list)
    assert len(activities) == 2
    # Ordered by activity_date ascending.
    assert [a["activity_date"] for a in activities] == [
        "2025-10-05",
        "2025-10-19",
    ]
    for activity in activities:
        assert set(activity) >= {
            "activity_id",
            "activity_date",
            "distance_km",
            "decoupling_pct",
            "pace_fade_pct",
        }
        assert isinstance(activity["activity_id"], int)
        assert isinstance(activity["distance_km"], (int, float))
        assert activity["distance_km"] >= 10.0
        assert isinstance(activity["decoupling_pct"], (int, float))
        assert isinstance(activity["pace_fade_pct"], (int, float))
        # Back half costs more HR per unit speed -> positive decoupling.
        assert activity["decoupling_pct"] > 0

    # Trend block: slope + data_points + direction classification.
    trend = payload["trend"]
    assert set(trend) >= {
        "decoupling_slope_per_day",
        "data_points",
        "direction",
    }
    assert isinstance(trend["decoupling_slope_per_day"], (int, float))
    assert trend["data_points"] == 2
    assert trend["direction"] in {
        "improving",
        "worsening",
        "stable",
        "insufficient_data",
    }


@pytest.mark.integration
def test_durability_endpoint_includes_form_fade(durability_db_path):
    """The endpoint surfaces #368 per-activity form fades + trend form fields."""
    client = TestClient(create_app(db_path=durability_db_path))
    response = client.get(
        "/api/durability-trend",
        params={"start_date": "2025-10-01", "end_date": "2025-10-31"},
    )

    assert response.status_code == 200
    payload = response.json()

    activities = payload["activities"]
    assert len(activities) == 2
    for activity in activities:
        assert set(activity) >= {
            "gct_fade_pct",
            "vo_fade_pct",
            "vr_fade_pct",
        }
        # GCT rises in the second half of both seeded long runs.
        assert isinstance(activity["gct_fade_pct"], (int, float))
        assert activity["gct_fade_pct"] > 0
        # VO/VR not seeded -> null.
        assert activity["vo_fade_pct"] is None
        assert activity["vr_fade_pct"] is None

    trend = payload["trend"]
    assert set(trend) >= {"gct_fade_slope_per_day", "form_direction"}
    # Only 2 form-bearing runs in range; the >=3-point gate (a5a9b66) yields
    # insufficient_data rather than a degenerate 2-point regression.
    assert trend["gct_fade_slope_per_day"] is None
    assert trend["form_direction"] in {
        "improving",
        "worsening",
        "stable",
        "insufficient_data",
    }


@pytest.mark.integration
def test_durability_trend_empty(durability_empty_db_path):
    client = TestClient(create_app(db_path=durability_empty_db_path))
    response = client.get(
        "/api/durability-trend",
        params={"start_date": "2025-10-01", "end_date": "2025-10-31"},
    )

    assert response.status_code == 200
    payload = response.json()

    # No qualifying long runs -> empty activities, insufficient_data trend.
    assert payload["activities"] == []
    assert payload["trend"]["direction"] == "insufficient_data"
    assert payload["trend"]["data_points"] == 0
