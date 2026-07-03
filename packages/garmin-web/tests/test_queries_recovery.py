"""Unit tests for garmin_web.queries.recovery conn-passing (Issue #719).

Recovery queries now take an open DuckDB connection (single-connection per
request) instead of a db_path, matching the rest of the queries/ layer. The
reader is built with ``GarminDBReader.from_connection(conn)`` so it reuses the
request's connection for its centralized reads.
"""

import re
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

import garmin_web.queries.recovery as recovery_queries
from garmin_web.app import create_app
from garmin_web.queries.recovery import get_recovery_status, get_recovery_trend

_CREATE_DAILY_WELLNESS = """
    CREATE TABLE daily_wellness (
        wellness_id INTEGER PRIMARY KEY,
        date DATE NOT NULL,
        resting_hr INTEGER,
        hrv_overnight_ms DOUBLE,
        hrv_status VARCHAR,
        hrv_baseline_low DOUBLE,
        hrv_baseline_high DOUBLE,
        sleep_seconds INTEGER,
        sleep_score INTEGER,
        training_readiness INTEGER,
        body_battery_high INTEGER,
        body_battery_low INTEGER,
        stress_avg INTEGER,
        source VARCHAR
    )
"""

# (date, resting_hr, hrv_ms, hrv_low, hrv_high, sleep, readiness, bb_high)
# Seven ascending days; the last two nights dip below the HRV baseline band so
# the under-recovery marker is exercised.
_WELLNESS_ROWS = [
    ("2025-10-01", 48, 65.0, 55.0, 80.0, 82, 78, 90),
    ("2025-10-02", 47, 68.0, 55.0, 80.0, 80, 80, 92),
    ("2025-10-03", 49, 70.0, 55.0, 80.0, 78, 76, 88),
    ("2025-10-04", 48, 66.0, 55.0, 80.0, 79, 77, 89),
    ("2025-10-05", 49, 64.0, 55.0, 80.0, 77, 75, 87),
    ("2025-10-06", 50, 52.0, 55.0, 80.0, 70, 70, 75),  # below baseline
    ("2025-10-07", 51, 50.0, 55.0, 80.0, 72, 72, 78),  # below baseline (latest)
]


@pytest.fixture
def wellness_conn():
    """In-memory DuckDB with daily_wellness + 7 ascending days of rows."""
    conn = duckdb.connect(":memory:")
    conn.execute(_CREATE_DAILY_WELLNESS)
    conn.executemany(
        "INSERT INTO daily_wellness ("
        "wellness_id, date, resting_hr, hrv_overnight_ms, hrv_status,"
        " hrv_baseline_low, hrv_baseline_high, sleep_score,"
        " training_readiness, body_battery_high"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                idx + 1,
                date,
                rhr,
                hrv,
                "balanced",
                low,
                high,
                sleep,
                readiness,
                bb_high,
            )
            for idx, (
                date,
                rhr,
                hrv,
                low,
                high,
                sleep,
                readiness,
                bb_high,
            ) in enumerate(_WELLNESS_ROWS)
        ],
    )
    yield conn
    conn.close()


@pytest.mark.unit
def test_recovery_status_with_conn(wellness_conn):
    """get_recovery_status(conn) returns the full status dict for the latest day."""
    result = get_recovery_status(wellness_conn)

    assert set(result) >= {
        "date",
        "recommendation",
        "score",
        "reasons",
        "training_readiness",
        "body_battery_high",
        "sleep_score",
    }
    # Latest day (2025-10-07) is picked when date is omitted.
    assert result["date"] == "2025-10-07"
    assert isinstance(result["reasons"], list)
    assert result["training_readiness"] == 72
    assert result["body_battery_high"] == 78
    assert result["sleep_score"] == 72


@pytest.mark.unit
def test_recovery_trend_with_conn(wellness_conn):
    """get_recovery_trend(conn) returns a date-ascending series + rhr/hrv blocks."""
    result = get_recovery_trend(wellness_conn, weeks=520)

    assert set(result) >= {"weeks", "rhr", "hrv", "series"}

    series = result["series"]
    assert isinstance(series, list)
    assert len(series) == len(_WELLNESS_ROWS)
    assert [p["date"] for p in series] == sorted(p["date"] for p in series)
    for point in series:
        assert set(point) >= {"date", "resting_hr", "hrv_overnight_ms"}

    assert set(result["rhr"]) >= {"median_7d", "median_30d", "rhr_trend"}
    hrv = result["hrv"]
    assert set(hrv) >= {
        "latest_ms",
        "status",
        "hrv_below_baseline_days",
        "under_recovery",
    }
    # The last two nights sit below the baseline band.
    assert hrv["hrv_below_baseline_days"] == 2
    assert hrv["under_recovery"] is True


@pytest.mark.integration
def test_recovery_endpoint_regression(recovery_db_path):
    """/api/recovery-status still returns 200 + the established response contract."""
    client = TestClient(create_app(db_path=recovery_db_path))
    response = client.get("/api/recovery-status")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "date",
        "recommendation",
        "score",
        "reasons",
        "training_readiness",
        "body_battery_high",
        "sleep_score",
    }
    assert isinstance(payload["reasons"], list)
    # A populated latest day yields a concrete (non-unknown) recommendation.
    assert payload["recommendation"] in {"rest", "easy", "moderate", "quality"}


@pytest.mark.unit
def test_no_dbpath_reader_construction_left():
    """No direct ``GarminDBReader(...)`` construction remains in queries/.

    Recovery queries must delegate via ``GarminDBReader.from_connection(conn)``
    (single-connection mode), never rebuild a reader from a request db_path.
    """
    queries_dir = Path(recovery_queries.__file__).parent
    pattern = re.compile(r"GarminDBReader\s*\(")
    offenders = [
        py.name
        for py in sorted(queries_dir.glob("*.py"))
        if pattern.search(py.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"Direct GarminDBReader(...) construction in: {offenders}"
