"""Tests for the trend-narration trigger detector in scheduled_sync (issue #792)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis
from garmin_mcp.ingest.catch_up import find_pending_trend_period
from garmin_mcp.scripts import scheduled_sync

# A fixed reference date so the detector's "last completed week" is deterministic.
TODAY = date(2026, 6, 24)


@pytest.mark.integration
def test_pending_returns_period_on_gap(initialized_db_path: Path) -> None:
    """No narration row -> the OLDEST completed week in the window is returned.

    Detection scans the last 4 completed weeks oldest-first (issue #1025), so an
    empty ``trend_analyses`` surfaces the 4th-most-recent completed week.
    """
    result = find_pending_trend_period(str(initialized_db_path), TODAY)

    assert result is not None
    assert result["granularity"] == "week"
    start = date.fromisoformat(result["period_start"])
    end = date.fromisoformat(result["period_end"])
    # Default week-start is Monday, so the pending week starts on a Monday...
    assert start.weekday() == 0
    # ...spans exactly 7 days (Mon..Sun)...
    assert (end - start).days == 6
    # ...and is the 4th completed week before the one containing TODAY.
    assert start.toordinal() + 28 <= TODAY.toordinal() < start.toordinal() + 35


@pytest.mark.integration
def test_pending_returns_last_completed_week_with_lookback_one(
    initialized_db_path: Path,
) -> None:
    """lookback_weeks=1 keeps the legacy "week that just ended" behaviour."""
    result = find_pending_trend_period(
        str(initialized_db_path), TODAY, lookback_weeks=1
    )

    assert result is not None
    start = date.fromisoformat(result["period_start"])
    assert start.weekday() == 0
    assert start.toordinal() + 7 <= TODAY.toordinal() < start.toordinal() + 14


@pytest.mark.integration
def test_pending_skips_when_row_exists(initialized_db_path: Path) -> None:
    """Narrating each surfaced week walks the window and then returns None.

    Detection is idempotent per week: inserting the returned period's row makes
    the next-newer pending week surface, and once all 4 scanned weeks have rows
    the detector returns None.
    """
    narrated: list[str] = []
    for _ in range(4):
        pending = find_pending_trend_period(str(initialized_db_path), TODAY)
        assert pending is not None
        narrated.append(pending["period_start"])
        insert_trend_analysis(
            {
                "granularity": "week",
                "period_start": pending["period_start"],
                "period_end": pending["period_end"],
                "analysis_data": {"narrative": "既存"},
            },
            db_path=str(initialized_db_path),
        )

    # Oldest first, one week apart, ending on the week that just completed.
    assert narrated == sorted(narrated)
    assert find_pending_trend_period(str(initialized_db_path), TODAY) is None


@pytest.mark.integration
def test_pending_uses_week_start_day(initialized_db_path: Path) -> None:
    """week_start_day=6 (Sunday) -> the pending week starts on a Sunday."""
    conn = duckdb.connect(str(initialized_db_path))
    conn.execute(
        "INSERT INTO athlete_profile (user_id, week_start_day) VALUES ('default', 6)"
    )
    conn.close()

    result = find_pending_trend_period(
        str(initialized_db_path), TODAY, lookback_weeks=1
    )

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
