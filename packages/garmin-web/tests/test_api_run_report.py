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
    "next_session",
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
def test_api_run_report_passes_axis_segments(
    detail_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structure-derived plan axes reach the page unchanged (#1407).

    The row shape is frozen in #1404 (``{axis, label_ja, target, actual,
    status, on_plan, verdict, segments[]}``); the endpoint must forward every
    key, including the per-step ``segments`` the card lists under the row.
    """
    stages = {
        "axis": "stages",
        "label_ja": "段階的ビルドアップ",
        "target": "130-140 → 140-150 bpm",
        "actual": "135 → 146 bpm",
        "status": "on_plan",
        "on_plan": True,
        "verdict": "✅",
        "segments": [
            {
                "segment_id": "1",
                "label": "第1段",
                "target": "130-140 bpm",
                "actual": "135 bpm",
                "on_plan": True,
            },
            {
                "segment_id": "2",
                "label": "第2段",
                "target": "140-150 bpm",
                "actual": "146 bpm",
                "on_plan": True,
            },
        ],
    }
    insufficient = {
        "axis": "hr_band_2",
        "label_ja": "心拍帯",
        "target": "150-160 bpm",
        "actual": "-",
        "status": "insufficient",
        "on_plan": False,
        "verdict": "✅",
        "segments": [],
    }
    seeded = {
        "activity_id": FULL_ACTIVITY_ID,
        "plan": {
            "verdict": "✅",
            "title": "ビルドアップ",
            "checks": [stages, insufficient],
            "hr_ceiling": None,
        },
    }
    monkeypatch.setattr(
        "garmin_web.api.activity_detail.get_run_report",
        lambda _conn, activity_id: seeded if activity_id == FULL_ACTIVITY_ID else None,
    )
    client = TestClient(create_app(db_path=detail_db_path))

    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}/report")

    assert response.status_code == 200
    checks = response.json()["plan"]["checks"]
    assert checks == [stages, insufficient]
    assert [len(check["segments"]) for check in checks] == [2, 0]
    assert checks[0]["segments"][1]["label"] == "第2段"


@pytest.mark.integration
def test_api_run_report_404(detail_db_path: Path) -> None:
    """An activity the database has never seen is a 404, not an empty report."""
    client = TestClient(create_app(db_path=detail_db_path))

    response = client.get("/api/activities/999999/report")

    assert response.status_code == 404
