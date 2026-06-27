"""API tests for the form-anomaly "今週の注意点" flags endpoint (Issue #636).

``detect_form_anomalies_summary`` reads each activity's raw
``raw/activity/<id>/activity_details.json`` relative to the detector base path
(the db file's grandparent). These tests therefore build a data tree with both
the DuckDB ``activities`` table and the matching raw time series so the
roll-up exercises the real detector end-to-end.
"""

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        activity_name VARCHAR,
        total_distance_km DOUBLE,
        total_time_seconds INTEGER,
        avg_pace_seconds_per_km DOUBLE,
        avg_heart_rate INTEGER
    )
"""

# Metric descriptors matching the raw Garmin activity_details.json layout the
# detector parses: HR, speed (factor 0.1 -> m/s), GCT (ms), VO (factor 10 -> cm).
_METRIC_DESCRIPTORS = [
    {"metricsIndex": 0, "key": "directHeartRate", "unit": {"id": 100, "key": "bpm", "factor": 1.0}},
    {"metricsIndex": 1, "key": "directSpeed", "unit": {"id": 20, "key": "mps", "factor": 0.1}},
    {"metricsIndex": 2, "key": "directGroundContactTime", "unit": {"id": 40, "key": "ms", "factor": 1.0}},
    {"metricsIndex": 3, "key": "directVerticalOscillation", "unit": {"id": 200, "key": "cm", "factor": 10.0}},
]

_SERIES_LEN = 80


def _write_activity_details(base_path: Path, activity_id: int, gct_series: list[float]) -> None:
    """Write a raw activity_details.json with a controllable GCT series.

    HR / speed / VO are held constant so only the GCT series can flag an anomaly.
    """
    rows = [
        {"metrics": [140, 28, gct, 80]}  # raw speed 28 -> 2.8 m/s, VO 80 -> 8.0 cm
        for gct in gct_series
    ]
    payload = {
        "activityId": activity_id,
        "measurementCount": len(rows),
        "metricDescriptors": _METRIC_DESCRIPTORS,
        "activityDetailMetrics": rows,
    }
    activity_dir = base_path / "raw" / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)
    (activity_dir / "activity_details.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _normal_gct() -> list[float]:
    """Flat GCT series (std 0 in every window) -> no anomalies."""
    return [240.0] * _SERIES_LEN


def _anomalous_gct() -> list[float]:
    """Flat GCT with one sharp +90 ms spike -> a clear, material GCT anomaly."""
    series = [240.0] * _SERIES_LEN
    series[40] = 330.0
    return series


def _build_db(base_path: Path, activities: list[tuple[int, str]]) -> Path:
    """Create the DuckDB at <base>/database/garmin.duckdb with given runs."""
    db_dir = base_path / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "garmin.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.executemany(
            "INSERT INTO activities ("
            "activity_id, activity_date, activity_name, total_distance_km,"
            " total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (aid, adate, "Run", 8.0, 2880, 360.0, 140)
                for aid, adate in activities
            ],
        )
    finally:
        conn.close()
    return db_path


def _recent(days_ago: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()


@pytest.mark.integration
def test_form_anomaly_flags_endpoint_empty(tmp_path: Path):
    """A run with normal form data -> 200, empty flags, scanned > 0."""
    base = tmp_path
    db_path = _build_db(base, [(9100000001, _recent(1))])
    _write_activity_details(base, 9100000001, _normal_gct())

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/form-anomaly-flags")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"weeks", "scanned", "limited", "flags"}
    assert payload["flags"] == []
    assert payload["scanned"] > 0
    assert payload["limited"] is False


@pytest.mark.integration
def test_form_anomaly_flags_detects_anomalous_run(tmp_path: Path):
    """A run with a GCT spike -> flagged with anomalies_detected > 0."""
    base = tmp_path
    db_path = _build_db(base, [(9100000002, _recent(2))])
    _write_activity_details(base, 9100000002, _anomalous_gct())

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/form-anomaly-flags")

    assert response.status_code == 200
    payload = response.json()

    flagged_ids = {f["activity_id"] for f in payload["flags"]}
    assert 9100000002 in flagged_ids

    flag = next(f for f in payload["flags"] if f["activity_id"] == 9100000002)
    assert flag["anomalies_detected"] > 0
    assert set(flag) >= {
        "activity_id",
        "activity_date",
        "anomalies_detected",
        "severity_high",
        "top_recommendation",
    }


@pytest.mark.integration
def test_form_anomaly_flags_respects_max_activities(tmp_path: Path):
    """5 runs in the window, max_activities=2 -> scanned <= 2, limited True."""
    base = tmp_path
    activities = [(9100000010 + i, _recent(i + 1)) for i in range(5)]
    db_path = _build_db(base, activities)
    for aid, _ in activities:
        _write_activity_details(base, aid, _normal_gct())

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/form-anomaly-flags?max_activities=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scanned"] <= 2
    assert payload["limited"] is True
