"""Unit tests for daily_wellness row mapping and insertion (issue #498).

Covers :func:`_wellness_row` field mapping / null-safety and
:meth:`GarminDBWriter.insert_daily_wellness` date-level idempotency.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from garmin_mcp.database.db_writer import GarminDBWriter, _wellness_row


def _full_wellness() -> dict:
    """A merged wellness payload with all four sections populated."""
    return {
        "stats": {
            "restingHeartRate": 48,
            "bodyBatteryHighestValue": 90,
            "bodyBatteryLowestValue": 20,
            "averageStressLevel": 32,
        },
        "hrv": {
            "hrvSummary": {
                "lastNightAvg": 62,
                "status": "BALANCED",
                "baseline": {"lowUpper": 55, "balancedUpper": 75},
            }
        },
        "sleep": {
            "dailySleepDTO": {
                "sleepTimeSeconds": 27000,
                "sleepScores": {"overall": {"value": 81}},
            }
        },
        "training_readiness": [{"score": 74}],
    }


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with schema pre-initialized."""
    tmp_path: Path = tmp_path_factory.mktemp("wellness_db_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB copied from the schema template."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


@pytest.mark.unit
def test_wellness_row_maps_all_fields() -> None:
    """All four sections populated → every column mapped correctly."""
    row = _wellness_row("2026-06-22", _full_wellness())

    assert row is not None
    assert row["date"] == "2026-06-22"
    assert row["resting_hr"] == 48
    assert row["hrv_overnight_ms"] == 62
    assert row["hrv_status"] == "BALANCED"
    assert row["hrv_baseline_low"] == 55
    assert row["hrv_baseline_high"] == 75
    assert row["sleep_seconds"] == 27000
    assert row["sleep_score"] == 81
    assert row["training_readiness"] == 74
    assert row["body_battery_high"] == 90
    assert row["body_battery_low"] == 20
    assert row["stress_avg"] == 32


@pytest.mark.unit
def test_wellness_row_returns_none_when_all_null() -> None:
    """Every endpoint empty → None (no metric to store)."""
    empty: dict = {"stats": {}, "hrv": {}, "sleep": {}, "training_readiness": []}
    assert _wellness_row("2026-06-22", empty) is None
    assert _wellness_row("2026-06-22", {}) is None


@pytest.mark.unit
def test_wellness_row_partial_device_off_day() -> None:
    """Only RHR present → resting_hr set, all other metrics None (null-safe)."""
    partial = {
        "stats": {"restingHeartRate": 50},
        "hrv": None,
        "sleep": None,
        "training_readiness": None,
    }
    row = _wellness_row("2026-06-22", partial)

    assert row is not None
    assert row["resting_hr"] == 50
    assert row["hrv_overnight_ms"] is None
    assert row["hrv_status"] is None
    assert row["sleep_seconds"] is None
    assert row["sleep_score"] is None
    assert row["training_readiness"] is None
    assert row["body_battery_high"] is None
    assert row["stress_avg"] is None


@pytest.mark.unit
def test_insert_daily_wellness_idempotent(initialized_db_path: Path) -> None:
    """Inserting the same date twice keeps exactly one row (date upsert)."""
    writer = GarminDBWriter(db_path=str(initialized_db_path))

    assert writer.insert_daily_wellness("2026-06-22", _full_wellness()) is True
    # Second insert with a different RHR for the same date.
    second = _full_wellness()
    second["stats"]["restingHeartRate"] = 51
    assert writer.insert_daily_wellness("2026-06-22", second) is True

    from garmin_mcp.database.connection import get_connection

    with get_connection(str(initialized_db_path)) as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM daily_wellness WHERE date = ?", ["2026-06-22"]
        ).fetchone()
        rhr_row = conn.execute(
            "SELECT resting_hr FROM daily_wellness WHERE date = ?", ["2026-06-22"]
        ).fetchone()

    assert count_row is not None and count_row[0] == 1
    assert rhr_row is not None and rhr_row[0] == 51
