"""Integration tests for GarminDBReader.get_recovery_trend (#499).

Builds a tmp DuckDB (schema via ``reader_db_path``), inserts ~8 weeks of
daily_wellness rows, then asserts the reader returns the rhr/hrv/series shape
with json.dumps-able, in-range values (RHR 35-90, HRV 20-120ms). No real data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_wellness(
    db_path: Path,
    *,
    wellness_id: int,
    date: str,
    resting_hr: int | None,
    hrv_overnight_ms: float | None,
    hrv_baseline_low: float | None,
    hrv_baseline_high: float | None,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO daily_wellness "
            "(wellness_id, date, resting_hr, hrv_overnight_ms, "
            "hrv_baseline_low, hrv_baseline_high) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                wellness_id,
                date,
                resting_hr,
                hrv_overnight_ms,
                hrv_baseline_low,
                hrv_baseline_high,
            ],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_recovery_trend_shape(reader_db_path: Path) -> None:
    """56 daily rows -> rhr/hrv/series keys, json-serializable, values in range
    (RHR 35-90, HRV 20-120ms)."""
    today = datetime.now()
    for i in range(56):
        d = (today - timedelta(days=55 - i)).strftime("%Y-%m-%d")
        _insert_wellness(
            reader_db_path,
            wellness_id=i + 1,
            date=d,
            resting_hr=50 - (i // 28),  # mild downward drift
            hrv_overnight_ms=60.0 + (i % 5),
            hrv_baseline_low=55.0,
            hrv_baseline_high=75.0,
        )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_recovery_trend(weeks=8)

    # Top-level shape.
    assert set(result.keys()) == {"weeks", "rhr", "hrv", "series"}
    assert result["weeks"] == 8

    # rhr block keys + value ranges.
    rhr = result["rhr"]
    assert set(rhr.keys()) == {"median_7d", "median_30d", "rhr_trend"}
    assert 35.0 <= rhr["median_7d"] <= 90.0
    assert 35.0 <= rhr["median_30d"] <= 90.0
    assert rhr["rhr_trend"] in {"improving", "fatigued", "stable"}

    # hrv block keys + value ranges.
    hrv = result["hrv"]
    assert set(hrv.keys()) == {
        "latest_ms",
        "status",
        "hrv_below_baseline_days",
        "under_recovery",
    }
    assert 20.0 <= hrv["latest_ms"] <= 120.0
    assert isinstance(hrv["under_recovery"], bool)
    assert hrv["hrv_below_baseline_days"] >= 0

    # series entries: keys + ranges, date-ascending.
    assert len(result["series"]) >= 1
    for entry in result["series"]:
        assert set(entry.keys()) == {"date", "resting_hr", "hrv_overnight_ms"}
        assert 35 <= entry["resting_hr"] <= 90
        assert 20.0 <= entry["hrv_overnight_ms"] <= 120.0
    dates = [e["date"] for e in result["series"]]
    assert dates == sorted(dates)

    # MCP-boundary serializable.
    json.dumps(result, default=str)


@pytest.mark.integration
def test_get_recovery_trend_empty(reader_db_path: Path) -> None:
    """Empty daily_wellness -> empty series, None medians, not under-recovery."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_recovery_trend(weeks=8)

    assert result["series"] == []
    assert result["rhr"]["median_7d"] is None
    assert result["rhr"]["rhr_trend"] == "stable"
    assert result["hrv"]["under_recovery"] is False
    assert result["hrv"]["latest_ms"] is None
    json.dumps(result, default=str)
