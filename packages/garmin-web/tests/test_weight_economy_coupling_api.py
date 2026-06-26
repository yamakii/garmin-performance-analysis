"""API tests for the weight-economy-coupling endpoint (Issue #556).

The Web layer is a thin pass-through to ``GarminDBReader.get_weight_economy_coupling``
(#554): the reader joins easy runs to nearby body-weight measurements and fits the
longitudinal ``EF ~ weight + days (+ fitness)`` association model. Fixtures are built
with raw ``duckdb.connect`` (the documented conftest exception) so each DB carries
only the columns the reader touches.
"""

import datetime as _dt
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        avg_speed_ms DOUBLE,
        avg_heart_rate INTEGER
    )
"""

_CREATE_HR_EFFICIENCY = """
    CREATE TABLE hr_efficiency (
        activity_id BIGINT PRIMARY KEY,
        training_type VARCHAR
    )
"""

_CREATE_BODY_COMPOSITION = """
    CREATE TABLE body_composition (
        measurement_id INTEGER PRIMARY KEY,
        date DATE NOT NULL,
        weight_kg DOUBLE
    )
"""

_CREATE_VO2_MAX = """
    CREATE TABLE vo2_max (
        activity_id BIGINT PRIMARY KEY,
        value DOUBLE,
        date DATE
    )
"""


def _create_coupling_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_CREATE_ACTIVITIES)
    conn.execute(_CREATE_HR_EFFICIENCY)
    conn.execute(_CREATE_BODY_COMPOSITION)
    conn.execute(_CREATE_VO2_MAX)


@pytest.fixture
def weight_economy_db_path(tmp_path: Path) -> Path:
    """DuckDB with 6 easy runs each matched to a same-day weight measurement.

    Weight falls from 80.0 to 78.5 kg over recent dates while speed varies, so the
    OLS regression is well-conditioned (n=6 >= n_params+2 with no fitness covariate)
    and the reader returns a non-null ``model``.
    """
    db_path = tmp_path / "test_garmin_web_weight_economy.duckdb"
    today = _dt.date.today()
    # (days_ago, avg_speed_ms, avg_heart_rate, weight_kg)
    samples = [
        (60, 2.55, 145, 80.0),
        (50, 2.58, 144, 79.6),
        (40, 2.60, 146, 79.2),
        (30, 2.63, 143, 79.0),
        (20, 2.66, 145, 78.7),
        (10, 2.70, 142, 78.5),
    ]
    conn = duckdb.connect(str(db_path))
    try:
        _create_coupling_tables(conn)
        for idx, (days_ago, speed, hr, weight) in enumerate(samples, start=1):
            day = (today - _dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")
            activity_id = 9000008000 + idx
            conn.execute(
                "INSERT INTO activities VALUES (?, ?, ?, ?)",
                [activity_id, day, speed, hr],
            )
            conn.execute(
                "INSERT INTO hr_efficiency VALUES (?, ?)",
                [activity_id, "aerobic_base"],
            )
            conn.execute(
                "INSERT INTO body_composition (measurement_id, date, weight_kg)"
                " VALUES (?, ?, ?)",
                [idx, day, weight],
            )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_weight_economy_db_path(tmp_path: Path) -> Path:
    """DuckDB with the coupling tables present but no aerobic_base runs.

    A non-easy run exists with no body-weight rows, so nothing matches: the
    reader must return ``model=None`` / ``series=[]`` (never raise / 500).
    """
    db_path = tmp_path / "test_garmin_web_weight_economy_empty.duckdb"
    today = _dt.date.today()
    conn = duckdb.connect(str(db_path))
    try:
        _create_coupling_tables(conn)
        day = (today - _dt.timedelta(days=5)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO activities VALUES (?, ?, ?, ?)",
            [9000008900, day, 3.2, 160],
        )
        conn.execute(
            "INSERT INTO hr_efficiency VALUES (?, ?)",
            [9000008900, "tempo"],
        )
    finally:
        conn.close()
    return db_path


@pytest.mark.integration
def test_weight_economy_coupling_endpoint_happy_path(weight_economy_db_path):
    client = TestClient(create_app(db_path=weight_economy_db_path))
    response = client.get("/api/weight-economy-coupling?weeks=26")

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) >= {"weeks", "n_matched", "series", "model", "note"}
    assert payload["weeks"] == 26

    # Every easy run is coupled to a same-day weight: 6 series points.
    series = payload["series"]
    assert isinstance(series, list)
    assert len(series) == 6
    for point in series:
        assert set(point) >= {
            "activity_id",
            "run_date",
            "weight_kg",
            "ef",
            "weight_gap_days",
        }

    # Enough matched runs -> the longitudinal model is fitted (non-null) and
    # reports the 5 kg-loss effect size + a (collinearity) association note.
    model = payload["model"]
    assert model is not None
    assert model["n"] == 6
    assert "delta_ef_per_5kg_loss" in model
    assert isinstance(model["collinearity_flag"], bool)
    assert model["weight"]["coef"] is not None
    assert isinstance(payload["note"], str) and payload["note"]


@pytest.mark.integration
def test_weight_economy_coupling_endpoint_empty_match(empty_weight_economy_db_path):
    client = TestClient(create_app(db_path=empty_weight_economy_db_path))
    response = client.get("/api/weight-economy-coupling?weeks=26")

    # No matched runs must degrade gracefully (200, not 500).
    assert response.status_code == 200
    payload = response.json()

    assert payload["model"] is None
    assert payload["series"] == []
    assert payload["n_matched"] == 0
