"""API tests for the wellness-baseline-deviation endpoint (Issue #635).

The Web layer is a thin pass-through to
``GarminDBReader.get_wellness_baseline_deviation`` (#555): the reader builds a
rolling personal band (mean +/- SD over the trailing ``window_days``) for HRV,
Training Readiness and resting HR from ``daily_wellness`` and judges the target
day against its own band as a z-score. Fixtures are built with raw
``duckdb.connect`` (the documented conftest exception) so each DB carries only
the columns the reader touches.
"""

import datetime as _dt
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_CREATE_DAILY_WELLNESS = """
    CREATE TABLE daily_wellness (
        wellness_id INTEGER PRIMARY KEY,
        date DATE NOT NULL,
        resting_hr INTEGER,
        hrv_overnight_ms DOUBLE,
        training_readiness INTEGER
    )
"""


def _seed_wellness(
    db_path: Path,
    *,
    today_hrv: float,
    today_readiness: int,
    today_rhr: int,
) -> None:
    """30 stable baseline days + a configurable target day at the tail.

    The trailing 30 days carry a tight band (hrv ~65, readiness ~75, rhr ~48)
    so the personal SD is small; the final day's values decide each metric's
    flag / adverse direction.
    """
    today = _dt.date.today()
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_DAILY_WELLNESS)
        # 30 trailing baseline days (today excluded), slight jitter for non-zero SD.
        for i in range(30, 0, -1):
            day = (today - _dt.timedelta(days=i)).strftime("%Y-%m-%d")
            hrv = 65.0 + (1.0 if i % 2 == 0 else -1.0)
            readiness = 75 + (1 if i % 2 == 0 else -1)
            rhr = 48 + (1 if i % 2 == 0 else -1)
            conn.execute(
                "INSERT INTO daily_wellness "
                "(wellness_id, date, resting_hr, hrv_overnight_ms, training_readiness)"
                " VALUES (?, ?, ?, ?, ?)",
                [i, day, rhr, hrv, readiness],
            )
        conn.execute(
            "INSERT INTO daily_wellness "
            "(wellness_id, date, resting_hr, hrv_overnight_ms, training_readiness)"
            " VALUES (?, ?, ?, ?, ?)",
            [0, today.strftime("%Y-%m-%d"), today_rhr, today_hrv, today_readiness],
        )
    finally:
        conn.close()


@pytest.fixture
def within_band_db_path(tmp_path: Path) -> Path:
    """Target day sitting inside every metric's personal band (no adverse flag)."""
    db_path = tmp_path / "test_garmin_web_wellness_within.duckdb"
    _seed_wellness(db_path, today_hrv=65.0, today_readiness=75, today_rhr=48)
    return db_path


@pytest.fixture
def adverse_db_path(tmp_path: Path) -> Path:
    """Target day with HRV crashed far below band -> adverse low + overall flag."""
    db_path = tmp_path / "test_garmin_web_wellness_adverse.duckdb"
    # HRV plunges well below the ~65 band; readiness / rhr stay within.
    _seed_wellness(db_path, today_hrv=40.0, today_readiness=75, today_rhr=48)
    return db_path


@pytest.mark.integration
def test_wellness_baseline_deviation_endpoint(within_band_db_path):
    client = TestClient(create_app(db_path=within_band_db_path))
    response = client.get("/api/wellness-baseline-deviation")

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) >= {"date", "hrv", "readiness", "rhr", "overall_flag"}
    assert payload["date"] == _dt.date.today().strftime("%Y-%m-%d")
    assert payload["overall_flag"] is False

    for metric in ("hrv", "readiness", "rhr"):
        block = payload[metric]
        assert set(block) >= {
            "metric",
            "mean",
            "std",
            "today",
            "z",
            "flag",
            "adverse",
            "n",
        }
        assert block["metric"] == metric
        assert block["n"] == 30
        assert block["flag"] in {"low", "high", "within", "insufficient"}
        assert block["adverse"] is False


@pytest.mark.integration
def test_wellness_baseline_overall_flag_true_when_adverse(adverse_db_path):
    client = TestClient(create_app(db_path=adverse_db_path))
    response = client.get("/api/wellness-baseline-deviation")

    assert response.status_code == 200
    payload = response.json()

    # HRV crashed below its band -> low + adverse, raising the overall flag.
    hrv = payload["hrv"]
    assert hrv["flag"] in {"low", "high"}
    assert hrv["flag"] == "low"
    assert hrv["adverse"] is True
    assert payload["overall_flag"] is True
