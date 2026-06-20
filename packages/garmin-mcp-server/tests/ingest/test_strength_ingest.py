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

from garmin_mcp.ingest.strength_ingest import (
    _aggregate_categories,
    _resolve_window,
    ingest_strength_sessions,
)

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


def _active_set(category: str) -> dict[str, Any]:
    """Build an ACTIVE set with the category nested under ``exercises[]``.

    Mirrors the real Garmin structure where ``category`` lives on each exercise
    rather than at the set level.
    """
    return {
        "setType": "ACTIVE",
        "repetitionCount": 12,
        "exercises": [{"category": category, "name": None}],
    }


def _exercise_sets() -> dict[str, Any]:
    """Exercise sets payload: 4 ACTIVE CRUNCH, 7 ACTIVE PLANK, plus REST.

    Uses the real nested structure (``exercises[].category``).
    """
    sets: list[dict[str, Any]] = []
    sets += [_active_set("CRUNCH") for _ in range(4)]
    sets += [_active_set("PLANK") for _ in range(7)]
    sets += [{"setType": "REST", "exercises": []} for _ in range(11)]
    return {"exerciseSets": sets}


@pytest.mark.unit
def test_aggregate_categories_nested_exercises() -> None:
    """ACTIVE sets with nested ``exercises[0].category`` are counted; REST is not."""
    payload = {
        "exerciseSets": [
            _active_set("CRUNCH"),
            _active_set("PLANK"),
            {"setType": "REST", "exercises": []},
        ]
    }
    assert _aggregate_categories(payload) == {"CRUNCH": 1, "PLANK": 1}


@pytest.mark.unit
def test_aggregate_categories_skips_unknown_and_empty() -> None:
    """ACTIVE sets with UNKNOWN category or no exercises are not counted."""
    payload = {
        "exerciseSets": [
            {
                "setType": "ACTIVE",
                "exercises": [{"category": "UNKNOWN", "name": None}],
            },
            {"setType": "ACTIVE", "exercises": []},
        ]
    }
    assert _aggregate_categories(payload) == {}


@pytest.mark.unit
def test_aggregate_categories_ignores_rest_sets() -> None:
    """A payload of only REST sets yields an empty dict."""
    payload = {
        "exerciseSets": [
            {"setType": "REST", "exercises": []},
            {"setType": "REST", "exercises": []},
        ]
    }
    assert _aggregate_categories(payload) == {}


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


# ---------------------------------------------------------------------------
# _resolve_window
# ---------------------------------------------------------------------------


def _seed_strength_row(db_path: Path, activity_id: int, activity_date: str) -> None:
    """Insert a minimal strength_sessions row so the latest date is set."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    GarminDBWriter(db_path=str(db_path))
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO strength_sessions (activity_id, activity_date)
            VALUES (?, ?)
            """,
            [activity_id, activity_date],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_resolve_window_empty_db_uses_30d_floor(temp_db_path: Path) -> None:
    """No stored strength date → start is end - 30 days."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    GarminDBWriter(db_path=str(temp_db_path))
    assert _resolve_window(None, "2026-06-20", str(temp_db_path)) == (
        "2026-05-21",
        "2026-06-20",
    )


@pytest.mark.integration
def test_resolve_window_from_latest(temp_db_path: Path) -> None:
    """Latest stored strength date is used as the (inclusive) window start."""
    _seed_strength_row(temp_db_path, 111, "2026-06-10")
    assert _resolve_window(None, "2026-06-20", str(temp_db_path)) == (
        "2026-06-10",
        "2026-06-20",
    )


@pytest.mark.unit
def test_resolve_window_end_defaults_today() -> None:
    """end_date=None resolves to today (start passed through)."""
    from datetime import date

    today = date.today().isoformat()
    start, end = _resolve_window("2026-06-01", None, "ignored.duckdb")
    assert start == "2026-06-01"
    assert end == today


@pytest.mark.unit
def test_resolve_window_explicit_range_passthrough() -> None:
    """Both dates explicit → returned unchanged (no DB access)."""
    assert _resolve_window("2026-06-01", "2026-06-30", "ignored.duckdb") == (
        "2026-06-01",
        "2026-06-30",
    )


# ---------------------------------------------------------------------------
# ingest_strength_sessions (catch-up)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ingest_catchup_uses_resolved_window(temp_db_path: Path) -> None:
    """Omitting start_date discovers from the latest stored date to end_date."""
    _seed_strength_row(temp_db_path, 111, "2026-06-10")
    client = _make_client([_strength_summary()])
    with patch(
        "garmin_mcp.ingest.strength_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_strength_sessions(
            end_date="2026-06-20", db_path=str(temp_db_path)
        )

    # Discovery was called with the catch-up window.
    client.get_activities_by_date.assert_called_once_with("2026-06-10", "2026-06-20")
    assert result["window"] == {"start": "2026-06-10", "end": "2026-06-20"}


@pytest.mark.integration
def test_ingest_explicit_range_unchanged(temp_db_path: Path) -> None:
    """Explicit range behaves as before: only the strength row is upserted."""
    client = _make_client([_run_summary(), _strength_summary()])
    with patch(
        "garmin_mcp.ingest.strength_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_strength_sessions(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    client.get_activities_by_date.assert_called_once_with("2026-06-01", "2026-06-30")
    assert result["inserted"] == 1
    assert result["activity_ids"] == [_STRENGTH_ACTIVITY_ID]
    assert result["window"] == {"start": "2026-06-01", "end": "2026-06-30"}
