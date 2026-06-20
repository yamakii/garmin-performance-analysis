"""Tests for the catch-up ingest orchestrator (issue #463).

The three per-domain ingest primitives are mocked (no Garmin / no real ingest):
each delegate is patched at its source module so the lazy imports inside
``catch_up`` resolve to the mock. Per-domain window resolution is exercised
against a seeded DuckDB (activities + strength_sessions rows, body_composition
empty) so the #460 ``get_latest_*_date`` readers return the seeded cursors.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.catch_up import catch_up_ingest


def _seed(db_path: Path) -> None:
    """Seed activities (latest 2026-06-18) and strength (latest 2026-06-10).

    body_composition is left empty so weight falls back to the 30-day floor.
    """
    GarminDBWriter(db_path=str(db_path))
    with get_write_connection(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, total_distance_km) "
            "VALUES (?, ?, ?)",
            [1001, "2026-06-15", 5.0],
        )
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, total_distance_km) "
            "VALUES (?, ?, ?)",
            [1002, "2026-06-18", 8.0],
        )
        conn.execute(
            "INSERT INTO strength_sessions (activity_id, activity_date) VALUES (?, ?)",
            [2001, "2026-06-05"],
        )
        conn.execute(
            "INSERT INTO strength_sessions (activity_id, activity_date) VALUES (?, ?)",
            [2002, "2026-06-10"],
        )


@pytest.mark.integration
def test_catch_up_resolves_per_domain_window(temp_db_path: Path) -> None:
    """Each domain resolves its own start from its latest stored date, and the
    weight domain (empty body_composition) falls back to end - 30 days."""
    _seed(temp_db_path)

    with (
        patch(
            "garmin_mcp.ingest.running_ingest.ingest_running_activities",
            return_value={"discovered": 0, "ingested": 0},
        ) as run_mock,
        patch(
            "garmin_mcp.ingest.weight_ingest.ingest_weight_range",
            return_value={"ingested_days": 0, "with_data": 0},
        ) as weight_mock,
        patch(
            "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions",
            return_value={"inserted": 0, "updated": 0},
        ) as strength_mock,
    ):
        result = catch_up_ingest(end_date="2026-06-20", db_path=str(temp_db_path))

    assert result["window"] == {
        "running": {"start": "2026-06-18", "end": "2026-06-20"},
        "strength": {"start": "2026-06-10", "end": "2026-06-20"},
        "weight": {"start": "2026-05-21", "end": "2026-06-20"},
    }

    run_mock.assert_called_once_with(
        "2026-06-18", "2026-06-20", db_path=str(temp_db_path)
    )
    weight_mock.assert_called_once_with(
        "2026-05-21", "2026-06-20", db_path=str(temp_db_path)
    )
    strength_mock.assert_called_once_with(
        "2026-06-10", "2026-06-20", db_path=str(temp_db_path)
    )


@pytest.mark.unit
def test_catch_up_end_defaults_today(temp_db_path: Path) -> None:
    """Omitting end_date resolves the shared window end to today."""
    # Create the (empty) schema so the latest-date readers can open the DB.
    GarminDBWriter(db_path=str(temp_db_path))
    today = date.today().isoformat()

    with (
        patch(
            "garmin_mcp.ingest.running_ingest.ingest_running_activities",
            return_value={},
        ),
        patch(
            "garmin_mcp.ingest.weight_ingest.ingest_weight_range",
            return_value={},
        ),
        patch(
            "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions",
            return_value={},
        ),
    ):
        result = catch_up_ingest(db_path=str(temp_db_path))

    for domain in ("running", "weight", "strength"):
        assert result["window"][domain]["end"] == today


@pytest.mark.integration
def test_catch_up_domains_subset(temp_db_path: Path) -> None:
    """domains=['weight'] runs only weight; running/strength are never called."""
    _seed(temp_db_path)

    with (
        patch(
            "garmin_mcp.ingest.running_ingest.ingest_running_activities",
        ) as run_mock,
        patch(
            "garmin_mcp.ingest.weight_ingest.ingest_weight_range",
            return_value={"ingested_days": 0, "with_data": 0},
        ) as weight_mock,
        patch(
            "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions",
        ) as strength_mock,
    ):
        result = catch_up_ingest(
            end_date="2026-06-20",
            domains=["weight"],
            db_path=str(temp_db_path),
        )

    weight_mock.assert_called_once()
    run_mock.assert_not_called()
    strength_mock.assert_not_called()

    assert set(result) == {"weight", "window"}
    assert set(result["window"]) == {"weight"}


@pytest.mark.integration
def test_catch_up_domain_error_isolated(temp_db_path: Path) -> None:
    """A failure in running is isolated: its entry carries an error while
    weight and strength complete normally."""
    _seed(temp_db_path)

    with (
        patch(
            "garmin_mcp.ingest.running_ingest.ingest_running_activities",
            side_effect=RuntimeError("garmin boom"),
        ),
        patch(
            "garmin_mcp.ingest.weight_ingest.ingest_weight_range",
            return_value={"ingested_days": 1, "with_data": 1},
        ),
        patch(
            "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions",
            return_value={"inserted": 2, "updated": 0},
        ),
    ):
        result = catch_up_ingest(end_date="2026-06-20", db_path=str(temp_db_path))

    assert result["running"] == {"error": "garmin boom"}
    assert result["weight"] == {"ingested_days": 1, "with_data": 1}
    assert result["strength"] == {"inserted": 2, "updated": 0}
    # Window is still recorded for the failed domain.
    assert result["window"]["running"] == {"start": "2026-06-18", "end": "2026-06-20"}
