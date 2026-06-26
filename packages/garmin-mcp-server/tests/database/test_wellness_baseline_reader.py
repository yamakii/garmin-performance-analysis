"""Integration tests for GarminDBReader.get_wellness_baseline_deviation (#555).

Builds a tmp DuckDB (schema via ``reader_db_path``), inserts daily_wellness rows,
then asserts the reader returns the hrv/readiness/rhr/overall_flag shape with
json.dumps-able, in-range values. No real data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader

_METRIC_KEYS = {"metric", "mean", "std", "today", "z", "flag", "adverse", "n"}


def _insert_wellness(
    db_path: Path,
    *,
    wellness_id: int,
    date: str,
    resting_hr: int | None,
    hrv_overnight_ms: float | None,
    training_readiness: int | None,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO daily_wellness "
            "(wellness_id, date, resting_hr, hrv_overnight_ms, training_readiness) "
            "VALUES (?, ?, ?, ?, ?)",
            [wellness_id, date, resting_hr, hrv_overnight_ms, training_readiness],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_e2e_get_wellness_baseline_deviation_shape(reader_db_path: Path) -> None:
    """30 history days + today -> hrv/readiness/rhr/overall_flag keys, json-safe,
    values in range (HRV ms positive, RHR 30-90)."""
    today = datetime.now()
    for i in range(31):
        d = (today - timedelta(days=30 - i)).strftime("%Y-%m-%d")
        _insert_wellness(
            reader_db_path,
            wellness_id=i + 1,
            date=d,
            resting_hr=50 + (i % 3),
            hrv_overnight_ms=60.0 + (i % 5),
            training_readiness=70 + (i % 4),
        )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_wellness_baseline_deviation()

    assert set(result.keys()) == {"date", "hrv", "readiness", "rhr", "overall_flag"}
    assert isinstance(result["overall_flag"], bool)

    for key in ("hrv", "readiness", "rhr"):
        block = result[key]
        assert set(block.keys()) == _METRIC_KEYS
        assert block["flag"] in {"low", "high", "within", "insufficient"}
        assert isinstance(block["adverse"], bool)
        assert block["n"] >= 0

    # Value ranges for the computed bands.
    assert result["hrv"]["mean"] > 0
    assert 30.0 <= result["rhr"]["mean"] <= 90.0

    # MCP-boundary serializable.
    json.dumps(result, default=str)


@pytest.mark.integration
def test_e2e_get_wellness_baseline_deviation_insufficient(reader_db_path: Path) -> None:
    """Only 4 rows -> each metric flag='insufficient', no exception, overall False."""
    today = datetime.now()
    for i in range(4):
        d = (today - timedelta(days=3 - i)).strftime("%Y-%m-%d")
        _insert_wellness(
            reader_db_path,
            wellness_id=i + 1,
            date=d,
            resting_hr=50,
            hrv_overnight_ms=60.0,
            training_readiness=70,
        )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_wellness_baseline_deviation()

    for key in ("hrv", "readiness", "rhr"):
        assert result[key]["flag"] == "insufficient"
        assert result[key]["mean"] is None
    assert result["overall_flag"] is False
    json.dumps(result, default=str)
