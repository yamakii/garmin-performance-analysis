"""API tests for the single-run report endpoint (#1250).

``GET /api/activities/{id}/report`` delegates to
``GarminDBReader.get_run_report`` (the Web package must never import
``garmin_mcp.rag``), so these tests assert the payload shape the page is built
from and the 404 an unknown activity must produce. The detail fixture DB
deliberately carries no ``hr_efficiency`` / ``weekly_prescriptions`` table,
which also pins the degradation an incomplete database has to survive.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

# Mirrors conftest.FULL_ACTIVITY_ID (fully-populated detail fixture row).
FULL_ACTIVITY_ID = 9000000101

_REPORT_KEYS = {
    "activity_id",
    "activity_date",
    "intensity_category",
    "headline",
    "plan",
    "signals",
    "zones",
    "moments",
    "flow",
    "recurrence",
    "phases",
    "conditions",
    "vs_previous",
    "next_run_target",
}


@pytest.mark.integration
def test_api_run_report_ok(detail_db_path: Path) -> None:
    """A known activity returns the whole report in one response."""
    client = TestClient(create_app(db_path=detail_db_path))

    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}/report")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= _REPORT_KEYS
    assert payload["activity_id"] == FULL_ACTIVITY_ID
    assert payload["headline"]["plan_label"] == "処方なし"
    assert [zone["zone"] for zone in payload["zones"]] == [1, 2, 3, 4, 5]
    assert payload["moments"], "five splits always yield at least one scene"
    assert payload["flow"]["axis"] in {"distance", "time"}
    assert payload["flow"]["segments"], "the page draws the shipped series"
    assert len(payload["signals"]) == 7
    assert set(payload["conditions"]) == {
        "temp_c",
        "humidity_pct",
        "wind_mps",
        "terrain",
        "elevation_gain_m",
    }


@pytest.mark.integration
def test_api_run_report_404(detail_db_path: Path) -> None:
    """An activity the database has never seen is a 404, not an empty report."""
    client = TestClient(create_app(db_path=detail_db_path))

    response = client.get("/api/activities/999999/report")

    assert response.status_code == 404
