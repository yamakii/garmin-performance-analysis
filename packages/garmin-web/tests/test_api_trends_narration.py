"""API tests for GET /api/trends/narration[/versions]."""

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_CREATE_TREND_ANALYSES = """
    CREATE TABLE trend_analyses (
        analysis_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        granularity VARCHAR NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        analysis_data VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        agent_name VARCHAR,
        agent_version VARCHAR
    )
"""


def _seed(
    conn: duckdb.DuckDBPyConnection,
    *,
    analysis_id: int,
    period_start: str,
    period_end: str,
    created_at: str,
    marker: str,
) -> None:
    conn.execute(
        "INSERT INTO trend_analyses ("
        "analysis_id, user_id, granularity, period_start, period_end,"
        " analysis_data, created_at, agent_name, agent_version"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            analysis_id,
            "default",
            "week",
            period_start,
            period_end,
            json.dumps({"narrative": marker}, ensure_ascii=False),
            created_at,
            "trend-narration",
            "1.0",
        ],
    )


@pytest.fixture
def narration_db_path(tmp_path: Path) -> Path:
    """trend_analyses with two versions of a single week."""
    db_path = tmp_path / "trends_narration_api.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_TREND_ANALYSES)
        _seed(
            conn,
            analysis_id=1,
            period_start="2025-10-06",
            period_end="2025-10-12",
            created_at="2025-10-13 10:00:00",
            marker="v1",
        )
        _seed(
            conn,
            analysis_id=2,
            period_start="2025-10-06",
            period_end="2025-10-12",
            created_at="2025-10-14 10:00:00",
            marker="v2",
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_narration_db_path(tmp_path: Path) -> Path:
    """Empty trend_analyses table."""
    db_path = tmp_path / "trends_narration_api_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_TREND_ANALYSES)
    finally:
        conn.close()
    return db_path


@pytest.mark.integration
def test_api_trend_narration_returns_latest(narration_db_path):
    client = TestClient(create_app(db_path=narration_db_path))
    response = client.get("/api/trends/narration", params={"granularity": "week"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["period_start"] == "2025-10-06"
    # latest version wins
    assert payload["analysis_data"]["narrative"] == "v2"


@pytest.mark.integration
def test_api_trend_narration_404_when_missing(empty_narration_db_path):
    client = TestClient(create_app(db_path=empty_narration_db_path))
    response = client.get("/api/trends/narration", params={"granularity": "week"})

    assert response.status_code == 404


@pytest.mark.integration
def test_api_trend_narration_rejects_bad_granularity(narration_db_path):
    client = TestClient(create_app(db_path=narration_db_path))
    response = client.get("/api/trends/narration", params={"granularity": "day"})

    assert response.status_code == 422


@pytest.mark.integration
def test_api_trend_narration_versions_empty_returns_200(empty_narration_db_path):
    client = TestClient(create_app(db_path=empty_narration_db_path))
    response = client.get(
        "/api/trends/narration/versions",
        params={"granularity": "week", "period_start": "2099-01-01"},
    )

    assert response.status_code == 200
    assert response.json() == []
