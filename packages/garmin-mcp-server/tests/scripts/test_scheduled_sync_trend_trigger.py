"""Tests for the trend-narration trigger detector in scheduled_sync (issue #792)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis
from garmin_mcp.ingest.catch_up import find_pending_trend_period
from garmin_mcp.scripts import scheduled_sync


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with full schema (base + migrations)."""
    tmp_path = tmp_path_factory.mktemp("trend_trigger_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB copy with schema pre-initialized."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


# A fixed reference date so the detector's "last completed week" is deterministic.
TODAY = date(2026, 6, 24)


@pytest.mark.integration
def test_pending_returns_period_on_gap(initialized_db_path: Path) -> None:
    """No narration row -> the immediately-preceding completed week is returned."""
    result = find_pending_trend_period(str(initialized_db_path), TODAY)

    assert result is not None
    assert result["granularity"] == "week"
    start = date.fromisoformat(result["period_start"])
    end = date.fromisoformat(result["period_end"])
    # Default week-start is Monday, so the pending week starts on a Monday...
    assert start.weekday() == 0
    # ...spans exactly 7 days (Mon..Sun)...
    assert (end - start).days == 6
    # ...and is the week immediately before the one containing TODAY.
    assert start.toordinal() + 7 <= TODAY.toordinal() < start.toordinal() + 14


@pytest.mark.integration
def test_pending_skips_when_row_exists(initialized_db_path: Path) -> None:
    """An existing (week, period_start) row makes detection return None (idempotent)."""
    pending = find_pending_trend_period(str(initialized_db_path), TODAY)
    assert pending is not None

    insert_trend_analysis(
        {
            "granularity": "week",
            "period_start": pending["period_start"],
            "period_end": pending["period_end"],
            "analysis_data": {"narrative": "既存"},
        },
        db_path=str(initialized_db_path),
    )

    assert find_pending_trend_period(str(initialized_db_path), TODAY) is None


@pytest.mark.integration
def test_pending_uses_week_start_day(initialized_db_path: Path) -> None:
    """week_start_day=6 (Sunday) -> the pending week starts on a Sunday."""
    conn = duckdb.connect(str(initialized_db_path))
    conn.execute(
        "INSERT INTO athlete_profile (user_id, week_start_day) VALUES ('default', 6)"
    )
    conn.close()

    result = find_pending_trend_period(str(initialized_db_path), TODAY)

    assert result is not None
    start = date.fromisoformat(result["period_start"])
    end = date.fromisoformat(result["period_end"])
    assert start.weekday() == 6  # Sunday
    assert (end - start).days == 6
    assert start.toordinal() + 7 <= TODAY.toordinal() < start.toordinal() + 14


_ALL_OK = {
    "running": {"activities_ingested": 1},
    "weight": {"days_ingested": 0},
    "strength": {"sessions_ingested": 0},
    "wellness": {"days_ingested": 0},
}


@pytest.mark.integration
def test_run_sync_records_pending_only_on_success(initialized_db_path: Path) -> None:
    """run_sync passes through the trend_pending that catch_up_ingest attaches.

    Detection now lives inside ``catch_up_ingest`` (issue #810), so run_sync
    records whatever it returns: a fully-successful run carries trend_pending,
    a partial run does not.
    """
    clean = {
        **_ALL_OK,
        "trend_pending": {
            "granularity": "week",
            "period_start": "2026-06-15",
            "period_end": "2026-06-21",
        },
    }
    with patch.object(scheduled_sync, "catch_up_ingest", return_value=clean):
        outcome = scheduled_sync.run_sync(db_path=str(initialized_db_path))
    assert outcome["status"] == "success"
    assert outcome["results"]["trend_pending"]["granularity"] == "week"

    partial = {"running": {"error": "boom"}, "weight": {"days_ingested": 1}}
    with patch.object(scheduled_sync, "catch_up_ingest", return_value=partial):
        outcome = scheduled_sync.run_sync(db_path=str(initialized_db_path))
    assert outcome["status"] == "partial"
    assert "trend_pending" not in outcome["results"]
