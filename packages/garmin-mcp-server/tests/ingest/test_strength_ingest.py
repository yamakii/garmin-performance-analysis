"""Integration tests for strength-session ingest (補強).

The Garmin client is mocked (no network): ``get_activities_by_date`` returns a
synthetic activity list and ``get_activity_exercise_sets`` returns synthetic
exercise sets. Tests assert the upserted ``strength_sessions`` rows, idempotent
re-ingest, and that non-strength (distance run) entries are filtered out.

The summary fixture mirrors the real activity 23315203017 used in the Issue
test plan (avg_heart_rate == 98, active_sets == 20).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.ingest.strength_ingest import ingest_strength_sessions

_STRENGTH_ACTIVITY_ID = 23315203017


def _strength_summary() -> dict[str, Any]:
    """Garmin activity-list summary for the strength fixture activity."""
    return {
        "activityId": _STRENGTH_ACTIVITY_ID,
        "activityName": "Strength",
        "startTimeLocal": "2026-06-15 07:30:00",
        "activityType": {"typeKey": "strength_training"},
        "duration": 2400.0,
        "movingDuration": 1800.0,
        "averageHR": 98.0,
        "maxHR": 132.0,
        "calories": 210.0,
        "activeSets": 20,
        "totalSets": 24,
        "distance": 0.0,
    }


def _run_summary() -> dict[str, Any]:
    """Garmin activity-list summary for a distance run (must be filtered out)."""
    return {
        "activityId": 99999,
        "activityName": "Morning Run",
        "startTimeLocal": "2026-06-15 06:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 1800.0,
        "movingDuration": 1750.0,
        "averageHR": 145.0,
        "maxHR": 165.0,
        "calories": 400.0,
        "distance": 5000.0,
    }


def _exercise_sets() -> dict[str, Any]:
    """Exercise sets payload: 4 ACTIVE CRUNCH, 7 ACTIVE PLANK, plus REST."""
    sets: list[dict[str, Any]] = []
    sets += [{"setType": "ACTIVE", "category": "CRUNCH"} for _ in range(4)]
    sets += [{"setType": "ACTIVE", "category": "PLANK"} for _ in range(7)]
    sets += [{"setType": "REST", "category": None} for _ in range(11)]
    return {"exerciseSets": sets}


def _make_client(activities: list[dict[str, Any]]) -> MagicMock:
    """Build a mock Garmin client returning the given activity list."""
    client = MagicMock()
    client.get_activities_by_date.return_value = activities
    client.get_activity_exercise_sets.return_value = _exercise_sets()
    return client


def _fetch_row(db_path: Path, activity_id: int) -> tuple[Any, ...] | None:
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(
            """
            SELECT activity_id, avg_heart_rate, active_sets, category_counts
            FROM strength_sessions WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()
    finally:
        conn.close()


@pytest.mark.integration
def test_ingest_strength_sessions_inserts_summary(temp_db_path: Path) -> None:
    """Ingesting the strength fixture writes a row with the expected summary."""
    client = _make_client([_strength_summary()])
    with patch(
        "garmin_mcp.ingest.strength_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_strength_sessions(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["activity_ids"] == [_STRENGTH_ACTIVITY_ID]

    row = _fetch_row(temp_db_path, _STRENGTH_ACTIVITY_ID)
    assert row is not None
    assert row[1] == 98  # avg_heart_rate
    assert row[2] == 20  # active_sets
    # category_counts stored as JSON; DuckDB returns it as a JSON string.
    import json

    counts = json.loads(row[3])
    assert isinstance(counts, dict)
    assert counts == {"CRUNCH": 4, "PLANK": 7}


@pytest.mark.integration
def test_ingest_strength_sessions_idempotent(temp_db_path: Path) -> None:
    """Re-ingesting the same activity upserts (no duplicate; counted updated)."""
    client = _make_client([_strength_summary()])
    with patch(
        "garmin_mcp.ingest.strength_ingest.get_garmin_client", return_value=client
    ):
        first = ingest_strength_sessions(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )
        second = ingest_strength_sessions(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["updated"] == 1

    conn = duckdb.connect(str(temp_db_path))
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM strength_sessions WHERE activity_id = ?",
            [_STRENGTH_ACTIVITY_ID],
        ).fetchone()
    finally:
        conn.close()
    assert count_row is not None
    assert count_row[0] == 1


@pytest.mark.integration
def test_ingest_strength_sessions_filters_non_strength(temp_db_path: Path) -> None:
    """A mixed run + strength discovery only inserts the strength_training row."""
    client = _make_client([_run_summary(), _strength_summary()])
    with patch(
        "garmin_mcp.ingest.strength_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_strength_sessions(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert result["inserted"] == 1
    assert result["activity_ids"] == [_STRENGTH_ACTIVITY_ID]

    conn = duckdb.connect(str(temp_db_path))
    try:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT activity_id FROM strength_sessions"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert ids == [_STRENGTH_ACTIVITY_ID]
    assert 99999 not in ids
