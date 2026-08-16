"""Tests for hiking-session ingest (山行, issue #921).

The Garmin client is mocked (no network): ``get_activities_by_date`` returns a
synthetic activity list. Tests assert the type-key filter (hiking only), the
exists-first skip, the persisted row's field mapping (metres -> km) and that a
summary missing ``elevationLoss`` still inserts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.ingest.hiking_ingest import (
    _is_hiking,
    _resolve_window,
    ingest_hiking_sessions,
)

_HIKING_ACTIVITY_ID = 24100000001


def _hiking_summary(**overrides: Any) -> dict[str, Any]:
    """Garmin activity-list summary for the hiking fixture activity."""
    summary: dict[str, Any] = {
        "activityId": _HIKING_ACTIVITY_ID,
        "activityName": "丹沢 山行",
        "startTimeLocal": "2026-08-11 06:30:00",
        "activityType": {"typeKey": "hiking"},
        "duration": 18000.0,
        "movingDuration": 14400.0,
        "distance": 8000.0,
        "elevationGain": 750.0,
        "elevationLoss": 740.0,
        "averageHR": 112.0,
        "maxHR": 148.0,
        "calories": 1800.0,
    }
    summary.update(overrides)
    return summary


def _run_summary() -> dict[str, Any]:
    """Garmin activity-list summary for a distance run (must be filtered out)."""
    return {
        "activityId": 99999,
        "activityName": "Morning Run",
        "startTimeLocal": "2026-08-11 06:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 1800.0,
        "movingDuration": 1750.0,
        "distance": 5000.0,
        "averageHR": 145.0,
    }


def _strength_summary() -> dict[str, Any]:
    """Garmin activity-list summary for strength training (must be filtered out)."""
    return {
        "activityId": 88888,
        "activityName": "Strength",
        "startTimeLocal": "2026-08-11 20:00:00",
        "activityType": {"typeKey": "strength_training"},
        "duration": 2400.0,
        "movingDuration": 1800.0,
        "distance": 0.0,
        "averageHR": 98.0,
    }


def _make_client(activities: list[dict[str, Any]]) -> MagicMock:
    """Build a mock Garmin client returning the given activity list."""
    client = MagicMock()
    client.get_activities_by_date.return_value = activities
    return client


def _fetch_row(db_path: Path, activity_id: int) -> tuple[Any, ...] | None:
    conn = duckdb.connect(str(db_path))
    try:
        return conn.execute(
            """
            SELECT distance_km, duration_seconds, elapsed_duration_seconds,
                   elevation_gain_m, elevation_loss_m, avg_heart_rate,
                   max_heart_rate, calories, activity_date, activity_name
            FROM hiking_sessions WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()
    finally:
        conn.close()


@pytest.mark.unit
def test_is_hiking_matches_type_key_without_distance_guard() -> None:
    """typeKey decides; a hike's distance must not disqualify it."""
    assert _is_hiking(_hiking_summary()) is True
    assert _is_hiking(_run_summary()) is False
    assert _is_hiking({"activityType": None}) is False


@pytest.mark.unit
def test_is_hiking_accepts_mountaineering() -> None:
    """Garmin records alpine outings as ``mountaineering`` (issue #925)."""
    assert (
        _is_hiking(_hiking_summary(activityType={"typeKey": "mountaineering"})) is True
    )
    assert _is_hiking(_hiking_summary(activityType={"typeKey": "walking"})) is False


@pytest.mark.unit
def test_ingest_hiking_sessions_filters_typekey(temp_db_path: Path) -> None:
    """hiking + mountaineering + running + strength -> both hikes are stored."""
    mountaineering = _hiking_summary(
        activityId=_HIKING_ACTIVITY_ID + 1,
        activityName="Hakuba Mountaineering",
        activityType={"typeKey": "mountaineering"},
    )
    client = _make_client(
        [_run_summary(), _hiking_summary(), mountaineering, _strength_summary()]
    )
    with patch(
        "garmin_mcp.ingest.hiking_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_hiking_sessions(
            "2026-08-01", "2026-08-31", db_path=str(temp_db_path)
        )

    assert result["discovered"] == 2
    assert result["ingested"] == 2
    assert result["skipped_existing"] == 0
    assert result["activity_ids"] == [_HIKING_ACTIVITY_ID, _HIKING_ACTIVITY_ID + 1]

    conn = duckdb.connect(str(temp_db_path))
    try:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT activity_id FROM hiking_sessions ORDER BY activity_id"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert ids == [_HIKING_ACTIVITY_ID, _HIKING_ACTIVITY_ID + 1]


@pytest.mark.unit
def test_ingest_hiking_sessions_skips_existing(temp_db_path: Path) -> None:
    """An already-stored hike is skipped (no re-write, no duplicate row)."""
    client = _make_client([_hiking_summary(activityId=111)])
    with patch(
        "garmin_mcp.ingest.hiking_ingest.get_garmin_client", return_value=client
    ):
        first = ingest_hiking_sessions(
            "2026-08-01", "2026-08-31", db_path=str(temp_db_path)
        )
        second = ingest_hiking_sessions(
            "2026-08-01", "2026-08-31", db_path=str(temp_db_path)
        )

    assert first["ingested"] == 1
    assert second["ingested"] == 0
    assert second["skipped_existing"] == 1
    assert second["activity_ids"] == []

    conn = duckdb.connect(str(temp_db_path))
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM hiking_sessions WHERE activity_id = ?", [111]
        ).fetchone()
    finally:
        conn.close()
    assert count_row is not None
    assert count_row[0] == 1


@pytest.mark.unit
def test_ingest_hiking_row_fields(temp_db_path: Path) -> None:
    """Summary fields map onto the row (metres -> km, moving -> duration)."""
    client = _make_client([_hiking_summary()])
    with patch(
        "garmin_mcp.ingest.hiking_ingest.get_garmin_client", return_value=client
    ):
        ingest_hiking_sessions("2026-08-01", "2026-08-31", db_path=str(temp_db_path))

    row = _fetch_row(temp_db_path, _HIKING_ACTIVITY_ID)
    assert row is not None
    assert row[0] == pytest.approx(8.0)  # distance_km (8000 m / 1000)
    assert row[1] == 14400  # duration_seconds (movingDuration)
    assert row[2] == 18000  # elapsed_duration_seconds (duration)
    assert row[3] == pytest.approx(750.0)  # elevation_gain_m
    assert row[4] == pytest.approx(740.0)  # elevation_loss_m
    assert row[5] == 112  # avg_heart_rate
    assert row[6] == 148  # max_heart_rate
    assert row[7] == 1800  # calories
    assert str(row[8]) == "2026-08-11"  # activity_date (from startTimeLocal)
    assert row[9] == "丹沢 山行"


@pytest.mark.unit
def test_ingest_hiking_handles_missing_elevation_loss(temp_db_path: Path) -> None:
    """A summary without elevationLoss still inserts (column stays NULL)."""
    summary = _hiking_summary()
    del summary["elevationLoss"]
    client = _make_client([summary])
    with patch(
        "garmin_mcp.ingest.hiking_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_hiking_sessions(
            "2026-08-01", "2026-08-31", db_path=str(temp_db_path)
        )

    assert result["ingested"] == 1
    row = _fetch_row(temp_db_path, _HIKING_ACTIVITY_ID)
    assert row is not None
    assert row[4] is None  # elevation_loss_m
    assert row[3] == pytest.approx(750.0)  # gain still stored


# ---------------------------------------------------------------------------
# _resolve_window
# ---------------------------------------------------------------------------


def _seed_hiking_row(db_path: Path, activity_id: int, activity_date: str) -> None:
    """Insert a minimal hiking_sessions row so the latest date is set."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    GarminDBWriter(db_path=str(db_path))
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO hiking_sessions (activity_id, activity_date) VALUES (?, ?)",
            [activity_id, activity_date],
        )
    finally:
        conn.close()


@pytest.mark.unit
def test_resolve_window_explicit_range_passthrough() -> None:
    """Both dates explicit -> returned unchanged (no DB access)."""
    assert _resolve_window("2026-08-01", "2026-08-16", "ignored.duckdb") == (
        "2026-08-01",
        "2026-08-16",
    )


@pytest.mark.integration
def test_resolve_window_empty_db_uses_30d_floor(temp_db_path: Path) -> None:
    """No stored hiking date -> start is end - 30 days."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    GarminDBWriter(db_path=str(temp_db_path))
    assert _resolve_window(None, "2026-08-16", str(temp_db_path)) == (
        "2026-07-17",
        "2026-08-16",
    )


@pytest.mark.integration
def test_resolve_window_from_latest(temp_db_path: Path) -> None:
    """Latest stored hiking date is used as the (inclusive) window start."""
    _seed_hiking_row(temp_db_path, 222, "2026-08-11")
    assert _resolve_window(None, "2026-08-16", str(temp_db_path)) == (
        "2026-08-11",
        "2026-08-16",
    )


@pytest.mark.integration
def test_ingest_catchup_uses_resolved_window(temp_db_path: Path) -> None:
    """Omitting start_date discovers from the latest stored date to end_date."""
    _seed_hiking_row(temp_db_path, 222, "2026-08-11")
    client = _make_client([])
    with patch(
        "garmin_mcp.ingest.hiking_ingest.get_garmin_client", return_value=client
    ):
        result = ingest_hiking_sessions(
            end_date="2026-08-16", db_path=str(temp_db_path)
        )

    client.get_activities_by_date.assert_called_once_with("2026-08-11", "2026-08-16")
    assert result["window"] == {"start": "2026-08-11", "end": "2026-08-16"}
