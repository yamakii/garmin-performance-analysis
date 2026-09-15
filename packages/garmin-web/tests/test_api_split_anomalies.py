"""API tests for the per-split form-anomaly endpoint (#1132).

``GET /api/activities/{id}/split-anomalies`` delegates to
``GarminDBReader.get_split_form_anomalies`` (the Web package must never import
``garmin_mcp.rag``), so these tests run the real detector over seeded raw data
and assert the payload shape plus the "nothing to highlight" degradation an
unknown activity must produce.
"""

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_CREATE_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE,
        start_time_s INTEGER,
        end_time_s INTEGER
    )
"""

# Raw Garmin metric descriptors the detector parses: HR, speed (factor 0.1 ->
# m/s), GCT (ms), VO (factor 10 -> cm), elevation (m). The climb makes the GCT
# spike material (``elevation_change``) instead of isolated noise.
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
    {
        "metricsIndex": 4,
        "key": "directElevation",
        "unit": {"id": 300, "key": "m", "factor": 1.0},
    },
]

_SERIES_LEN = 600

# Three flagged seconds two apart span the detector's 5 s sustained minimum
# while leaving the ±30 s rolling window mostly clean, so the spike is scored
# instead of being absorbed into its own baseline.
_SPIKE_SECONDS = (400, 402, 404)

_SPLIT_KEYS = {
    "split_index",
    "anomalies",
    "material",
    "severity_high",
    "max_z",
    "metrics",
}


def _elevation(index: int) -> float:
    """Flat 10 m with a 2 m/s climb over seconds 396-410 (spans the spike)."""
    if index < 396:
        return 10.0
    if index > 410:
        return 38.0
    return 10.0 + 2.0 * (index - 396)


def _write_activity_details(base_path: Path, activity_id: int) -> None:
    """Write raw details: flat form metrics plus a GCT spike on a climb."""
    rows = [
        {
            "metrics": [
                140,
                28,
                290.0 if index in _SPIKE_SECONDS else 240.0,
                80,
                _elevation(index),
            ]
        }
        for index in range(_SERIES_LEN)
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


def _build_db(base_path: Path, activity_id: int) -> Path:
    """Create <base>/database/garmin.duckdb with two 300 s splits."""
    db_dir = base_path / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "garmin.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_SPLITS)
        conn.executemany(
            "INSERT INTO splits (activity_id, split_index, distance, "
            "duration_seconds, start_time_s, end_time_s) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (activity_id, 1, 1.0, 301.0, 0, 300),
                (activity_id, 2, 1.0, 300.0, 301, 600),
            ],
        )
    finally:
        conn.close()
    return db_path


@pytest.mark.integration
def test_api_split_anomalies_shape(tmp_path: Path):
    """200 with the activity totals and one fully-formed row per flagged split."""
    activity_id = 9600000001
    db_path = _build_db(tmp_path, activity_id)
    _write_activity_details(tmp_path, activity_id)

    client = TestClient(create_app(db_path=db_path))
    response = client.get(f"/api/activities/{activity_id}/split-anomalies")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"activity_id", "total", "material", "splits"}
    assert payload["activity_id"] == activity_id
    assert payload["splits"], "the seeded GCT spike should flag its split"
    for row in payload["splits"]:
        assert set(row) == _SPLIT_KEYS
    # The spike sits at 400-404 s, inside split 2 (301-600 s).
    assert [row["split_index"] for row in payload["splits"]] == [2]
    assert payload["total"] == sum(row["anomalies"] for row in payload["splits"])


@pytest.mark.integration
def test_api_split_anomalies_unknown_activity(tmp_path: Path):
    """An activity with no splits and no raw details is empty, not 404 / 500."""
    db_path = _build_db(tmp_path, 9600000002)

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/api/activities/9699999999/split-anomalies")

    assert response.status_code == 200
    assert response.json() == {
        "activity_id": 9699999999,
        "total": 0,
        "material": 0,
        "splits": [],
    }
