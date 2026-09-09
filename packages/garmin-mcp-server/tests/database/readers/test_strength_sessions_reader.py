"""Integration tests for StrengthSessionsReader (補強 summaries).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture),
inserts strength_sessions rows directly, then asserts the reader returns the
expected date-range slice with ``category_counts`` parsed to a dict and dates
as strings. No real data or Garmin access.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.strength_sessions import StrengthSessionsReader


def _insert_session(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    category_counts: dict[str, int],
    avg_heart_rate: int = 100,
) -> None:
    """Insert one strength_sessions row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO strength_sessions (
                activity_id, activity_date, start_time_local, activity_name,
                active_duration_seconds, elapsed_duration_seconds,
                avg_heart_rate, max_heart_rate, calories,
                active_sets, total_sets, category_counts, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                f"{activity_date} 07:00:00",
                "Strength",
                1800,
                2000,
                avg_heart_rate,
                140,
                200,
                20,
                24,
                json.dumps(category_counts),
                f"{activity_date} 08:00:00",
            ],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_strength_sessions_date_range(reader_db_path: Path) -> None:
    """Two in-range + one out-of-range -> only the two in-range are returned."""
    _insert_session(
        reader_db_path,
        activity_id=1001,
        activity_date="2026-06-10",
        category_counts={"CRUNCH": 4, "PLANK": 7},
    )
    _insert_session(
        reader_db_path,
        activity_id=1002,
        activity_date="2026-06-15",
        category_counts={"SQUAT": 3},
    )
    _insert_session(
        reader_db_path,
        activity_id=1003,
        activity_date="2026-07-01",
        category_counts={"LUNGE": 2},
    )

    reader = StrengthSessionsReader(db_path=str(reader_db_path))
    result = reader.get_strength_sessions("2026-06-01", "2026-06-30")

    assert [r["activity_id"] for r in result] == [1001, 1002]
    first = result[0]
    assert isinstance(first["category_counts"], dict)
    assert first["category_counts"] == {"CRUNCH": 4, "PLANK": 7}
    assert first["activity_date"] == "2026-06-10"
    assert isinstance(first["activity_date"], str)


@pytest.mark.integration
def test_get_strength_sessions_empty(reader_db_path: Path) -> None:
    """No matching session -> empty list (no exception)."""
    _insert_session(
        reader_db_path,
        activity_id=2001,
        activity_date="2026-01-05",
        category_counts={"CRUNCH": 1},
    )

    reader = StrengthSessionsReader(db_path=str(reader_db_path))
    result = reader.get_strength_sessions("2026-06-01", "2026-06-30")

    assert result == []
