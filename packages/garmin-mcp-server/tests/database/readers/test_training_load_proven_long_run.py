"""Integration tests for ``TrainingLoadReader.get_proven_long_run`` (#1568)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.readers.training_load import TrainingLoadReader

_BEFORE = "2026-11-02"


def _days_before(days: int) -> str:
    return str(date.fromisoformat(_BEFORE) - timedelta(days=days))


def _insert(db_path: Path, rows: list[tuple[int, str, float, int]]) -> None:
    with get_write_connection(str(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km, total_time_seconds
            ) VALUES (?, ?, ?, ?)
            """,
            rows,
        )


@pytest.mark.integration
def test_proven_long_run_picks_longest_in_window(reader_db_path: Path) -> None:
    """A 5 h run 400 days ago is outside the 180-day window; the 3 h run wins."""
    _insert(
        reader_db_path,
        [
            (156801, _days_before(100), 30.0, 3 * 3600),
            (156802, _days_before(400), 42.2, 5 * 3600),
            (156803, _days_before(20), 10.0, 3600),
            # On before_date itself: excluded (strictly earlier only).
            (156804, _BEFORE, 35.0, 4 * 3600),
        ],
    )

    proven = TrainingLoadReader(str(reader_db_path)).get_proven_long_run(_BEFORE)

    assert proven == {
        "duration_sec": 3 * 3600,
        "distance_km": 30.0,
        "activity_date": _days_before(100),
    }


@pytest.mark.integration
def test_proven_long_run_none_when_empty(reader_db_path: Path) -> None:
    """No run in the window -> None."""
    assert TrainingLoadReader(str(reader_db_path)).get_proven_long_run(_BEFORE) is None
