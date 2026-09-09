"""Tests for HikingSessionsReader / get_latest_hiking_date (山行, issue #921).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture),
inserts hiking_sessions rows directly, then asserts the reader returns the
expected date-range slice with dates as strings. No real data, no Garmin access.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.readers.hiking_sessions import HikingSessionsReader


def _insert_hike(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float = 8.0,
    elevation_gain_m: float = 750.0,
) -> None:
    """Insert one hiking_sessions row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO hiking_sessions (
                activity_id, activity_date, start_time_local, activity_name,
                duration_seconds, elapsed_duration_seconds, distance_km,
                elevation_gain_m, elevation_loss_m,
                avg_heart_rate, max_heart_rate, calories, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                f"{activity_date} 06:30:00",
                "山行",
                14400,
                18000,
                distance_km,
                elevation_gain_m,
                740.0,
                112,
                148,
                1800,
                f"{activity_date} 20:00:00",
            ],
        )
    finally:
        conn.close()


@pytest.mark.unit
def test_get_hiking_sessions_range(reader_db_path: Path) -> None:
    """One in-range + one out-of-range -> only the in-range hike, dates as str."""
    _insert_hike(reader_db_path, activity_id=3001, activity_date="2026-08-11")
    _insert_hike(reader_db_path, activity_id=3002, activity_date="2026-08-20")

    reader = HikingSessionsReader(db_path=str(reader_db_path))
    result = reader.get_hiking_sessions("2026-08-10", "2026-08-16")

    assert [r["activity_id"] for r in result] == [3001]
    first = result[0]
    assert isinstance(first["activity_date"], str)
    assert first["activity_date"] == "2026-08-11"
    assert first["distance_km"] == pytest.approx(8.0)
    assert first["elevation_gain_m"] == pytest.approx(750.0)
    assert isinstance(first["start_time_local"], str)


@pytest.mark.unit
def test_get_hiking_sessions_empty(reader_db_path: Path) -> None:
    """No matching hike -> empty list (no exception)."""
    _insert_hike(reader_db_path, activity_id=3003, activity_date="2026-01-05")

    reader = HikingSessionsReader(db_path=str(reader_db_path))
    assert reader.get_hiking_sessions("2026-08-01", "2026-08-31") == []


@pytest.mark.unit
def test_get_latest_hiking_date(reader_db_path: Path) -> None:
    """Empty table -> None; after one row -> that row's date as a string."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    assert reader.get_latest_hiking_date() is None

    _insert_hike(reader_db_path, activity_id=3004, activity_date="2026-08-11")

    assert reader.get_latest_hiking_date() == "2026-08-11"
