"""API tests for the form-anomaly "今週の注意点" flags endpoint (#636, #809).

The aggregation now lives in ``GarminDBReader.get_recent_form_anomaly_flags``;
the Web query is a thin delegator (#809). These tests cover (a) the delegation
wiring (the endpoint forwards ``weeks`` / ``max_activities`` and returns the
reader payload verbatim) and (b) an end-to-end pass where the real detector runs
over seeded raw data and an isolated-only run yields no flags.
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
    {
        "metricsIndex": 0,
        "key": "directHeartRate",
        "unit": {"id": 100, "key": "bpm", "factor": 1.0},
    },
    {
        "metricsIndex": 1,
        "key": "directSpeed",
        "unit": {"id": 20, "key": "mps", "factor": 0.1},
    },
    {
        "metricsIndex": 2,
        "key": "directGroundContactTime",
        "unit": {"id": 40, "key": "ms", "factor": 1.0},
    },
    {
        "metricsIndex": 3,
        "key": "directVerticalOscillation",
        "unit": {"id": 200, "key": "cm", "factor": 10.0},
    },
]

_SERIES_LEN = 80


def _write_activity_details_with_speed(
    base_path: Path,
    activity_id: int,
    gct_series: list[float],
    speed_series: list[int],
) -> None:
    """Write raw activity_details.json with controllable GCT and speed series.

    HR / VO are held constant; ``speed_series`` (raw, factor 0.1 -> m/s) lets a
    test inject (or withhold) a pace change so a GCT spike classifies as a
    *material* cause vs isolated noise (#666).
    """
    rows = [
        {"metrics": [140, speed, gct, 80]}
        for gct, speed in zip(gct_series, speed_series, strict=True)
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


def _anomalous_gct() -> list[float]:
    """Flat GCT with one sharp +90 ms spike -> a clear GCT anomaly."""
    series = [240.0] * _SERIES_LEN
    series[40] = 330.0
    return series


def _flat_speed() -> list[int]:
    """Constant speed (raw 28 -> 2.8 m/s) -> no pace change near a spike."""
    return [28] * _SERIES_LEN


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
            [(aid, adate, "Run", 8.0, 2880, 360.0, 140) for aid, adate in activities],
        )
    finally:
        conn.close()
    return db_path


def _recent(days_ago: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()


@pytest.mark.integration
def test_form_anomaly_flags_endpoint_empty(tmp_path: Path):
    """A GCT spike with flat context is isolated noise -> no flags (#666, end-to-end).

    The spike is real at the detector level but has no identifiable cause, so the
    reader's material-event scan yields zero material events and the card stays
    empty. Exercises the full web -> reader -> real-detector delegation.
    """
    base = tmp_path
    db_path = _build_db(base, [(9100000002, _recent(2))])
    _write_activity_details_with_speed(
        base, 9100000002, _anomalous_gct(), _flat_speed()
    )

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/form-anomaly-flags")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"weeks", "scanned", "limited", "flags"}
    assert payload["flags"] == []
    assert payload["scanned"] > 0
    assert payload["limited"] is False


@pytest.mark.integration
def test_flags_delegate_to_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The endpoint forwards weeks/max_activities and returns the reader payload."""
    base = tmp_path
    db_path = _build_db(base, [(9100000009, _recent(1))])

    captured: dict[str, int] = {}
    sentinel = {
        "weeks": 5,
        "scanned": 3,
        "limited": True,
        "flags": [{"activity_id": 42}],
    }

    def _fake(self, weeks: int = 2, max_activities: int = 12) -> dict:
        captured["weeks"] = weeks
        captured["max_activities"] = max_activities
        return sentinel

    monkeypatch.setattr(
        "garmin_web.queries.recovery.GarminDBReader.get_recent_form_anomaly_flags",
        _fake,
    )

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/form-anomaly-flags?weeks=5&max_activities=7")

    assert response.status_code == 200
    assert captured == {"weeks": 5, "max_activities": 7}
    assert response.json() == sentinel
