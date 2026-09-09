"""Unit tests for the long-run extension streak derivation (Issue #927).

``count_long_run_build_weeks`` is the primary cutback gate: it counts the
trailing streak of weekly longest-run extensions (>= +3%), tolerating a hold
(75%-103%) and stopping at a real cutback (< 75%) or a week with no run. These
tests pin the policy boundaries and the headline-metrics wiring.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.derivations import (
    LONG_RUN_CUTBACK_TRIGGER_WEEKS,
    compute_trend_headline_metrics,
    count_long_run_build_weeks,
)


@pytest.mark.unit
def test_long_run_build_weeks_three_extensions() -> None:
    """Three straight >= +3% extensions after a cutback week -> streak 3.

    Real series (2026-07-20 cutback -> 07-27 -> 08-03 -> 08-10): the volume
    streak read 2 while the long run had been extended three weeks running.
    """
    assert count_long_run_build_weeks([3250, 7819, 8125, 8562]) == 3


@pytest.mark.unit
def test_long_run_build_weeks_hold_preserves() -> None:
    """A hold (ratio in [0.75, 1.03)) neither extends nor resets the streak."""
    # 7800/7480 = 1.043 (+1); 7480/7500 = 0.997 (hold, keep walking back);
    # 7500/7200 = 1.042 (+1) -> 2.
    assert count_long_run_build_weeks([7200, 7500, 7480, 7800]) == 2


@pytest.mark.unit
def test_long_run_build_weeks_reset_on_cutback() -> None:
    """A drop below 75% is a real cutback and ends the walk."""
    # 7000/3000 = 2.33 (+1); 3000/8000 = 0.375 < 0.75 -> stop.
    assert count_long_run_build_weeks([8000, 3000, 7000]) == 1


@pytest.mark.unit
def test_long_run_build_weeks_edge_cases() -> None:
    """Empty / single-week / missing-week series yield 0."""
    assert count_long_run_build_weeks([]) == 0
    assert count_long_run_build_weeks([7200]) == 0
    # A week with no run is a reset boundary, so the walk stops immediately.
    assert count_long_run_build_weeks([7200, None, 7500]) == 0


@pytest.mark.unit
def test_headline_metrics_long_run_build_weeks() -> None:
    """The trend headline fold exposes long_run_build_weeks from load_trend."""
    context = {
        "load_trend": {
            "weeks": [
                {"week_start": "2026-07-20", "load_km": 20.0, "longest_run_sec": 3250},
                {"week_start": "2026-07-27", "load_km": 30.0, "longest_run_sec": 7819},
                {"week_start": "2026-08-03", "load_km": 28.0, "longest_run_sec": 8125},
                {"week_start": "2026-08-10", "load_km": 34.0, "longest_run_sec": 8562},
            ]
        }
    }

    result = compute_trend_headline_metrics(context)

    assert "long_run_build_weeks" in result
    assert result["long_run_build_weeks"] == 3
    assert result["long_run_build_weeks"] >= LONG_RUN_CUTBACK_TRIGGER_WEEKS
