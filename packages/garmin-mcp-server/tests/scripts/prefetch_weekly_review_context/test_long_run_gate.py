"""Long-run progression gate inside the weekly-review bundle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import (
    _MODULE,
    _mock_prefetch,
    _weeks,
)


@pytest.mark.unit
def test_prefetch_bundle_long_run_gate() -> None:
    """load_trend.long_run carries the deterministic cutback gate (#927)."""
    weekly_longest = [3250, 7819, 8125, 8562]
    # Four completed weeks, all before W (2026-07-06).
    week_starts = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29"]
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            list(zip(week_starts, weekly_longest, strict=True))
        )
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == weekly_longest
    # Three straight >= +3% extensions -> the primary cutback gate fires.
    assert long_run["long_run_build_weeks"] == 3
    assert long_run["cutback_due_long_run"] is True


@pytest.mark.unit
def test_long_run_gate_excludes_in_progress_week() -> None:
    """W's own partial bucket must not reset the streak (#929).

    ``get_load_trend`` ends at today, so a Monday review sees W's bucket with
    ``longest_run_sec: None`` (the week's long run has not happened yet). That
    ``None`` used to read as a no-run week and zero the gate.
    """
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            [
                ("2026-07-20", 3250),
                ("2026-07-27", 7819),
                ("2026-08-03", 8125),
                ("2026-08-10", 8562),
                ("2026-08-17", None),  # W itself, still in progress
            ]
        )
        result = prefetch_weekly_review_context("this", today="2026-08-17")

    assert result["week_start_date"] == "2026-08-17"
    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == [3250, 7819, 8125, 8562]
    assert long_run["long_run_build_weeks"] == 3
    assert long_run["cutback_due_long_run"] is True


@pytest.mark.unit
def test_long_run_gate_keeps_none_for_completed_norun_week() -> None:
    """A completed week with no run is still a reset boundary (#929)."""
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            [
                ("2026-07-27", 7200),
                ("2026-08-03", None),  # completed week, genuinely no run
                ("2026-08-10", 7500),
            ]
        )
        result = prefetch_weekly_review_context("this", today="2026-08-17")

    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == [7200, None, 7500]
    assert long_run["long_run_build_weeks"] == 0
    assert long_run["cutback_due_long_run"] is False


@pytest.mark.unit
def test_prefetch_weekly_review_long_run_gate() -> None:
    """W-1's longest run carries the progression verdict at load_trend (#982)."""
    prev_activities = [
        {
            "activity_id": 9101,
            "activity_date": "2026-06-30",
            "activity_name": "朝ジョグ",
            "distance_km": 8.0,
            "duration_seconds": 2600,
        },
        {
            "activity_id": 9102,
            "activity_date": "2026-07-05",
            "activity_name": "ロング走",
            "distance_km": 19.0,
            "duration_seconds": 7800,
        },
    ]
    gate = {
        "activity_id": 9102,
        "current": {"gct_fade_ms": 12.0},
        "reference": {"activity_id": 9003},
        "verdict": "yellow",
        "recommendation": "repeat",
        "triggers": [{"metric": "gct_fade_ms", "worse_than_reference": False}],
        "decoupling_contaminated": False,
        "reference_activity_id": 9003,
        "reason_ja": "次は同距離で反復してください。",
    }

    with (
        _mock_prefetch() as reader,
        patch(f"{_MODULE}._resolve_activities", side_effect=[prev_activities, []]),
        patch(f"{_MODULE}.build_long_run_progression_gate", return_value=gate) as build,
    ):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    long_run = result["load_trend"]["long_run"]
    assert long_run["gate"]["verdict"] == "yellow"
    assert long_run["gate"]["recommendation"] == "repeat"
    # The longest W-1 run is gated, not the 8 km jog.
    build.assert_called_once_with(reader, 9102)


@pytest.mark.unit
def test_prefetch_weekly_review_long_run_gate_null_without_long_run() -> None:
    """A W-1 with no run reaching 10 km leaves the gate null (#982)."""
    prev_activities = [
        {
            "activity_id": 9201,
            "activity_date": "2026-07-02",
            "activity_name": "朝ジョグ",
            "distance_km": 8.0,
            "duration_seconds": 2600,
        }
    ]

    with (
        _mock_prefetch(),
        patch(f"{_MODULE}._resolve_activities", side_effect=[prev_activities, []]),
        patch(f"{_MODULE}.build_long_run_progression_gate") as build,
    ):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["load_trend"]["long_run"]["gate"] is None
    build.assert_not_called()


@pytest.mark.unit
def test_prefetch_invalid_target_returns_error() -> None:
    """An unparseable target -> a fatal error bundle."""
    with (
        patch(f"{_MODULE}.get_db_path", return_value=Path("/tmp/wr_unit.duckdb")),
        patch(f"{_MODULE}.get_connection"),
        patch(f"{_MODULE}.get_week_start_day", return_value=0),
    ):
        result = prefetch_weekly_review_context("garbage", today="2026-07-10")

    assert "error" in result
    assert "garbage" in result["error"]
