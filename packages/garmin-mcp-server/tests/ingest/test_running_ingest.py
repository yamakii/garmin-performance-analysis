"""Integration tests for running differential ingest.

The Garmin client and ``GarminIngestWorker`` are mocked (no network, no file
I/O): ``get_activities_by_date`` returns a synthetic activity list and
``process_activity`` is a no-op MagicMock. Tests assert that runs are discovered
via the typeKey whitelist (strength filtered out), that already-ingested
activities are skipped, and that an empty discovery never touches the worker.
``time.sleep`` is patched so throttling adds no real delay.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.running_ingest import ingest_running_activities

_RUN_A = 30000000001
_RUN_B = 30000000002
_STRENGTH = 30000000003


def _run_summary(activity_id: int, date: str = "2026-06-15") -> dict[str, Any]:
    """Garmin activity-list summary for a distance run."""
    return {
        "activityId": activity_id,
        "activityName": "Morning Run",
        "startTimeLocal": f"{date} 06:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 1800.0,
        "distance": 5000.0,
    }


def _strength_summary(activity_id: int) -> dict[str, Any]:
    """Garmin activity-list summary for a strength session (must be filtered)."""
    return {
        "activityId": activity_id,
        "activityName": "Strength",
        "startTimeLocal": "2026-06-15 07:30:00",
        "activityType": {"typeKey": "strength_training"},
        "duration": 2400.0,
        "distance": 0.0,
    }


def _make_client(activities: list[dict[str, Any]]) -> MagicMock:
    """Build a mock Garmin client returning the given activity list."""
    client = MagicMock()
    client.get_activities_by_date.return_value = activities
    return client


def _seed_existing(db_path: Path, activity_id: int, date: str = "2026-06-15") -> None:
    """Insert a minimal pre-existing row into the ``activities`` table."""
    # Ensure the schema exists before seeding (mirrors ingest_running_activities).
    GarminDBWriter(db_path=str(db_path))
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
            [activity_id, date],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_ingest_running_discovers_and_filters(temp_db_path: Path) -> None:
    """List with 2 runs + 1 strength → only the 2 runs are targeted."""
    activities = [
        _run_summary(_RUN_A),
        _strength_summary(_STRENGTH),
        _run_summary(_RUN_B),
    ]
    client = _make_client(activities)
    worker = MagicMock()
    with (
        patch(
            "garmin_mcp.ingest.running_ingest.get_garmin_client",
            return_value=client,
        ),
        patch(
            "garmin_mcp.ingest.running_ingest.GarminIngestWorker",
            return_value=worker,
        ),
        patch("garmin_mcp.ingest.running_ingest.time.sleep"),
    ):
        result = ingest_running_activities(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert result["discovered"] == 2
    assert result["ingested"] == 2
    assert result["skipped_existing"] == 0
    assert result["activity_ids"] == [_RUN_A, _RUN_B]
    assert worker.process_activity.call_count == 2
    called_ids = [c.args[0] for c in worker.process_activity.call_args_list]
    assert _STRENGTH not in called_ids


@pytest.mark.integration
def test_ingest_running_skips_existing(temp_db_path: Path) -> None:
    """2 runs where 1 already exists in DB → ingested==1, skipped_existing==1."""
    _seed_existing(temp_db_path, _RUN_A)
    activities = [_run_summary(_RUN_A), _run_summary(_RUN_B)]
    client = _make_client(activities)
    worker = MagicMock()
    with (
        patch(
            "garmin_mcp.ingest.running_ingest.get_garmin_client",
            return_value=client,
        ),
        patch(
            "garmin_mcp.ingest.running_ingest.GarminIngestWorker",
            return_value=worker,
        ),
        patch("garmin_mcp.ingest.running_ingest.time.sleep"),
    ):
        result = ingest_running_activities(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert result["discovered"] == 2
    assert result["ingested"] == 1
    assert result["skipped_existing"] == 1
    assert result["activity_ids"] == [_RUN_B]
    assert worker.process_activity.call_count == 1
    assert worker.process_activity.call_args.args[0] == _RUN_B


@pytest.mark.integration
def test_ingest_running_empty_range(temp_db_path: Path) -> None:
    """Empty discovery → discovered==0 and process_activity never called."""
    client = _make_client([])
    worker = MagicMock()
    with (
        patch(
            "garmin_mcp.ingest.running_ingest.get_garmin_client",
            return_value=client,
        ),
        patch(
            "garmin_mcp.ingest.running_ingest.GarminIngestWorker",
            return_value=worker,
        ),
        patch("garmin_mcp.ingest.running_ingest.time.sleep"),
    ):
        result = ingest_running_activities(
            "2026-06-01", "2026-06-30", db_path=str(temp_db_path)
        )

    assert result["discovered"] == 0
    assert result["ingested"] == 0
    assert result["skipped_existing"] == 0
    assert result["activity_ids"] == []
    worker.process_activity.assert_not_called()
