"""Integration tests for garmin_web.queries.trends narration readers."""

import json
from pathlib import Path

import duckdb
import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.trends import (
    get_trend_narration,
    list_trend_narration_versions,
)

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
    granularity: str,
    period_start: str,
    period_end: str,
    created_at: str,
    marker: str,
) -> None:
    """Insert one trend_analyses version with an explicit created_at."""
    conn.execute(
        "INSERT INTO trend_analyses ("
        "analysis_id, user_id, granularity, period_start, period_end,"
        " analysis_data, created_at, agent_name, agent_version"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            analysis_id,
            "default",
            granularity,
            period_start,
            period_end,
            json.dumps({"narrative": marker}, ensure_ascii=False),
            created_at,
            "trend-narration",
            "1.0",
        ],
    )


def _make_db(tmp_path: Path, name: str) -> Path:
    db_path = tmp_path / name
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_TREND_ANALYSES)
    finally:
        conn.close()
    return db_path


@pytest.mark.integration
def test_get_trend_narration_returns_latest(tmp_path: Path):
    db_path = _make_db(tmp_path, "trends_narration.duckdb")
    conn = duckdb.connect(str(db_path))
    try:
        _seed(
            conn,
            analysis_id=1,
            granularity="week",
            period_start="2025-10-06",
            period_end="2025-10-12",
            created_at="2025-10-13 10:00:00",
            marker="v1",
        )
        _seed(
            conn,
            analysis_id=2,
            granularity="week",
            period_start="2025-10-06",
            period_end="2025-10-12",
            created_at="2025-10-14 10:00:00",
            marker="v2",
        )
    finally:
        conn.close()

    with get_connection(db_path) as conn:
        narration = get_trend_narration(conn, "week")

    assert narration is not None
    assert narration["period_start"] == "2025-10-06"
    # latest version (highest created_at) wins
    assert narration["analysis_data"]["narrative"] == "v2"
    # date/timestamp values are str
    assert isinstance(narration["period_start"], str)
    assert isinstance(narration["analysis_data"], dict)


@pytest.mark.integration
def test_get_trend_narration_none_when_empty(tmp_path: Path):
    db_path = _make_db(tmp_path, "trends_narration_empty.duckdb")
    with get_connection(db_path) as conn:
        narration = get_trend_narration(conn, "week")
    assert narration is None


@pytest.mark.integration
def test_list_trend_narration_versions_returns_all(tmp_path: Path):
    db_path = _make_db(tmp_path, "trends_narration_versions.duckdb")
    conn = duckdb.connect(str(db_path))
    try:
        for analysis_id, created_at, marker in [
            (1, "2025-10-13 10:00:00", "v1"),
            (2, "2025-10-14 10:00:00", "v2"),
            (3, "2025-10-15 10:00:00", "v3"),
        ]:
            _seed(
                conn,
                analysis_id=analysis_id,
                granularity="week",
                period_start="2025-10-06",
                period_end="2025-10-12",
                created_at=created_at,
                marker=marker,
            )
    finally:
        conn.close()

    with get_connection(db_path) as conn:
        versions = list_trend_narration_versions(conn, "week", "2025-10-06")

    assert len(versions) == 3
    # newest first (created_at DESC)
    created = [v["created_at"] for v in versions]
    assert created == sorted(created, reverse=True)
    assert versions[0]["analysis_data"]["narrative"] == "v3"
    assert isinstance(versions[0]["analysis_data"], dict)
