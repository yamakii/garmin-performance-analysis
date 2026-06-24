"""Integration tests for GarminDBReader.get_recovery_status (#500).

Builds a tmp DuckDB (schema via ``reader_db_path``), inserts daily_wellness rows
with today's go/no-go markers, then asserts the reader returns the
recommendation shape with json.dumps-able values. No real data.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_wellness(
    db_path: Path,
    *,
    wellness_id: int,
    date: str,
    training_readiness: int | None = None,
    body_battery_high: int | None = None,
    sleep_score: int | None = None,
    hrv_overnight_ms: float | None = None,
    hrv_baseline_low: float | None = None,
    hrv_baseline_high: float | None = None,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO daily_wellness "
            "(wellness_id, date, training_readiness, body_battery_high, "
            "sleep_score, hrv_overnight_ms, hrv_baseline_low, hrv_baseline_high) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                wellness_id,
                date,
                training_readiness,
                body_battery_high,
                sleep_score,
                hrv_overnight_ms,
                hrv_baseline_low,
                hrv_baseline_high,
            ],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_recovery_status_latest(reader_db_path: Path) -> None:
    """Latest day (no date arg) -> recommendation key present, json-serializable.

    Two days are inserted; the reader must pick the latest date and surface the
    raw markers alongside the recommendation.
    """
    _insert_wellness(
        reader_db_path,
        wellness_id=1,
        date="2026-06-22",
        training_readiness=60,
        body_battery_high=70,
        sleep_score=72,
        hrv_overnight_ms=62.0,
        hrv_baseline_low=55.0,
        hrv_baseline_high=75.0,
    )
    _insert_wellness(
        reader_db_path,
        wellness_id=2,
        date="2026-06-23",
        training_readiness=82,
        body_battery_high=90,
        sleep_score=85,
        hrv_overnight_ms=64.0,
        hrv_baseline_low=55.0,
        hrv_baseline_high=75.0,
    )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_recovery_status()

    assert set(result.keys()) == {
        "date",
        "recommendation",
        "score",
        "reasons",
        "training_readiness",
        "body_battery_high",
        "sleep_score",
    }
    assert result["date"] == "2026-06-23"
    assert result["recommendation"] in {
        "rest",
        "easy",
        "moderate",
        "quality",
        "unknown",
    }
    # High readiness + normal HRV -> quality.
    assert result["recommendation"] == "quality"
    assert result["training_readiness"] == 82
    assert isinstance(result["reasons"], list)

    json.dumps(result, default=str)


@pytest.mark.integration
def test_get_recovery_status_empty(reader_db_path: Path) -> None:
    """Empty daily_wellness -> unknown recommendation, null markers, json-able."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_recovery_status()

    assert result["date"] is None
    assert result["recommendation"] == "unknown"
    assert result["reasons"]
    assert result["training_readiness"] is None
    json.dumps(result, default=str)
