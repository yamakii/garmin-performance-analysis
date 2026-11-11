"""Unit tests for the proven-distance exemption of the long-run streak (#1568).

A return ladder climbing back inside a distance the athlete has already run in
the lookback window is not new stress, so only extensions whose longest run
exceeds the proven run count toward the cutback streak.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.derivations import (
    compute_trend_headline_metrics,
    count_long_run_build_weeks,
    long_run_cutback_gate,
    long_run_streak_start,
    proven_max_sec,
)


@pytest.mark.unit
def test_streak_unchanged_without_proven() -> None:
    """No proven run -> every >= +3% extension counts, as before."""
    assert count_long_run_build_weeks([3600, 4000, 4400, 4900], None) == 3


@pytest.mark.unit
def test_steps_inside_proven_not_counted() -> None:
    """Every step inside the proven 6000 s -> nothing counts."""
    assert (
        count_long_run_build_weeks([3600, 4000, 4400, 4900], proven_max_sec=6000) == 0
    )


@pytest.mark.unit
def test_only_steps_beyond_proven_count() -> None:
    """5500 is inside the proven 6000 s; 6200 and 6800 are beyond it."""
    assert (
        count_long_run_build_weeks([5000, 5500, 6200, 6800], proven_max_sec=6000) == 2
    )


@pytest.mark.unit
def test_none_week_still_resets() -> None:
    """A no-run week still ends the walk with a proven run in play.

    The Issue's ``[6200, None, 6800]`` reads 0 under the existing rule (the
    walk stops at once on the None, pinned by
    ``test_long_run_build_weeks_edge_cases``), so a counted step is placed
    after the None: 6800 / 6100 counts, then the None stops the walk before
    6200 can be reached.
    """
    assert (
        count_long_run_build_weeks([6200, None, 6100, 6800], proven_max_sec=6000) == 1
    )
    assert count_long_run_build_weeks([6200, None, 6800], proven_max_sec=6000) == 0


@pytest.mark.unit
def test_streak_start_is_first_plain_counted_week() -> None:
    """The proven run is measured before the plain streak's first week."""
    weeks = [
        {"week_start": "2026-10-05", "longest_run_sec": 3600},
        {"week_start": "2026-10-12", "longest_run_sec": 4000},
        {"week_start": "2026-10-19", "longest_run_sec": 4400},
    ]
    assert long_run_streak_start(weeks) == "2026-10-12"
    assert long_run_streak_start(weeks[:1]) is None


@pytest.mark.unit
def test_proven_max_sec_rejects_unusable_values() -> None:
    """Only a dict with a positive numeric duration reads as proven."""
    assert proven_max_sec({"duration_sec": 6000}) == 6000.0
    assert proven_max_sec(None) is None
    assert proven_max_sec({"duration_sec": None}) is None
    assert proven_max_sec({"duration_sec": 0}) is None
    assert proven_max_sec("6000") is None


@pytest.mark.unit
def test_gate_reason_names_proven_run_when_it_suppressed() -> None:
    """A due gate that skipped an inside step names the proven run."""
    weeks = [
        {"week_start": "2026-10-05", "longest_run_sec": 5000},
        {"week_start": "2026-10-12", "longest_run_sec": 5500},
        {"week_start": "2026-10-19", "longest_run_sec": 6200},
        {"week_start": "2026-10-26", "longest_run_sec": 6800},
        {"week_start": "2026-11-02", "longest_run_sec": 7400},
    ]
    proven = {"duration_sec": 6000, "distance_km": 14.0, "activity_date": "2026-08-02"}

    gate = long_run_cutback_gate(weeks, proven)

    assert gate["long_run_build_weeks"] == 3
    assert gate["cutback_due_long_run"] is True
    assert gate["proven_exempt_weeks"] == 1
    assert gate["proven_long_run"] == proven
    assert "8/2 の 14 km（100 分）" in gate["cutback_reason_ja"]
    assert "10/12" not in gate["cutback_reason_ja"]


@pytest.mark.unit
def test_headline_metrics_pass_proven_run() -> None:
    """The trend headline counts the same proven-filtered streak."""
    context = {
        "load_trend": {
            "weeks": [
                {"week_start": "2026-10-05", "load_km": 20, "longest_run_sec": 3600},
                {"week_start": "2026-10-12", "load_km": 22, "longest_run_sec": 4000},
                {"week_start": "2026-10-19", "load_km": 24, "longest_run_sec": 4400},
                {"week_start": "2026-10-26", "load_km": 26, "longest_run_sec": 4900},
            ]
        }
    }

    plain = compute_trend_headline_metrics(context)
    proven = compute_trend_headline_metrics(context, {"duration_sec": 6000})

    assert plain["cutback_due_long_run"] is True
    assert proven["long_run_build_weeks"] == 0
    assert proven["cutback_due_long_run"] is False
    assert proven["cutback_reason_ja"] is None
