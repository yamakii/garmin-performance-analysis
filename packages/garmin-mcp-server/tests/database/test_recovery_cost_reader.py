"""Integration tests for GarminDBReader.get_long_run_recovery_cost (#1218).

Builds a tmp DuckDB (schema via ``reader_db_path``), seeds one long run plus 17
days of daily_wellness around it, and asserts the reader picks d+1 / d+2 by date
arithmetic and builds the baseline from the days *before* the run. No real data.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader

_ACTIVITY_ID = 20718100001
_RUN_DATE = "2026-03-15"


def _seed(db_path: Path) -> None:
    """One 28 km run on 2026-03-15 + wellness for 2026-03-01 .. 2026-03-17."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name, "
            "total_distance_km, avg_heart_rate, temp_celsius) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [_ACTIVITY_ID, _RUN_DATE, "Long run", 28.6, 148, 8.0],
        )
        # 14 baseline mornings: flat RHR 45 / HRV 60.
        for i in range(1, 15):
            conn.execute(
                "INSERT INTO daily_wellness (wellness_id, date, resting_hr, "
                "hrv_overnight_ms, training_readiness, sleep_seconds, "
                "body_battery_low) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [i, f"2026-03-{i:02d}", 45, 60.0, 72, 25200, 30],
            )
        # The run day itself reads high; it must not enter the baseline.
        conn.execute(
            "INSERT INTO daily_wellness (wellness_id, date, resting_hr, "
            "hrv_overnight_ms, training_readiness, sleep_seconds, "
            "body_battery_low) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [15, _RUN_DATE, 60, 40.0, 30, 21600, 10],
        )
        # d+1 and d+2: RHR stays up, HRV down 16 %, readiness 29.
        conn.execute(
            "INSERT INTO daily_wellness (wellness_id, date, resting_hr, "
            "hrv_overnight_ms, training_readiness, sleep_seconds, "
            "body_battery_low) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [16, "2026-03-16", 48, 50.4, 29, 21600, 12],
        )
        conn.execute(
            "INSERT INTO daily_wellness (wellness_id, date, resting_hr, "
            "hrv_overnight_ms, training_readiness, sleep_seconds, "
            "body_battery_low) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [17, "2026-03-17", 49, 55.0, 45, 23400, 18],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_reader_joins_next_two_mornings(reader_db_path: Path) -> None:
    """d+1 / d+2 are picked by date arithmetic; the run day is out of the baseline."""
    _seed(reader_db_path)

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_long_run_recovery_cost(_ACTIVITY_ID)

    assert result is not None
    assert result["activity_id"] == _ACTIVITY_ID
    assert result["activity_date"] == _RUN_DATE
    assert result["distance_km"] == 28.6

    # 14 mornings before the run; the run day's own high RHR is excluded.
    assert result["baseline"] == {"rhr_median": 45.0, "hrv_median": 60.0, "n": 14}

    assert result["d1"]["date"] == "2026-03-16"
    assert result["d1"]["rhr_delta"] == 3.0
    assert result["d1"]["hrv_delta_pct"] == -16.0
    assert result["d1"]["readiness"] == 29
    assert result["d1"]["sleep_hours"] == 6.0
    assert result["d2"]["date"] == "2026-03-17"
    assert result["d2"]["rhr_delta"] == 4.0

    assert {c["name"] for c in result["criteria"] if c["fired"]} == {
        "rhr_two_day",
        "readiness",
        "hrv",
    }
    assert result["cost_flag"] is True
    assert result["insufficient_data"] is False

    # MCP-boundary serializable.
    json.dumps(result, default=str)


@pytest.mark.integration
def test_reader_unknown_activity_returns_none(reader_db_path: Path) -> None:
    """An activity_id that is not in the table yields None, not an empty verdict."""
    _seed(reader_db_path)

    reader = GarminDBReader(db_path=str(reader_db_path))

    assert reader.get_long_run_recovery_cost(999) is None
