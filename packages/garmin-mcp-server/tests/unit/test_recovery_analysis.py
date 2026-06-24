"""Unit tests for recovery analysis helpers (#499).

Pure functions only -- no I/O. Cover the RHR 7d/30d-median trend
(improving / fatigued / stable / insufficient data) and the HRV
below-baseline under-recovery counter.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.recovery import (
    compute_hrv_recovery,
    compute_rhr_trend,
)


@pytest.mark.unit
def test_rhr_trend_improving() -> None:
    """7d median ~46 vs 30d median ~49 -> 'improving' (cardio recovered)."""
    # 30 days: first 23 at 49, last 7 at 46 -> median_30d=49, median_7d=46.
    daily = [(f"2026-05-{i + 1:02d}", 49) for i in range(23)]
    daily += [(f"2026-06-{i + 1:02d}", 46) for i in range(7)]

    result = compute_rhr_trend(daily)

    assert result["median_7d"] == 46
    assert result["median_30d"] == 49
    assert result["rhr_trend"] == "improving"


@pytest.mark.unit
def test_rhr_trend_fatigued() -> None:
    """7d median 53 vs 30d median ~49 -> 'fatigued' (delta >= +3)."""
    daily = [(f"2026-05-{i + 1:02d}", 49) for i in range(23)]
    daily += [(f"2026-06-{i + 1:02d}", 53) for i in range(7)]

    result = compute_rhr_trend(daily)

    assert result["median_7d"] == 53
    assert result["median_30d"] == 49
    assert result["rhr_trend"] == "fatigued"


@pytest.mark.unit
def test_rhr_trend_stable_within_band() -> None:
    """7d median 49 == 30d median 49 -> 'stable'."""
    daily = [(f"2026-05-{i + 1:02d}", 49) for i in range(30)]

    result = compute_rhr_trend(daily)

    assert result["median_7d"] == 49
    assert result["median_30d"] == 49
    assert result["rhr_trend"] == "stable"


@pytest.mark.unit
def test_rhr_trend_insufficient_data() -> None:
    """Only 3 days -> medians computed from the available days, no exception."""
    daily = [
        ("2026-06-01", 48),
        ("2026-06-02", None),  # device-off day, skipped null-safe
        ("2026-06-03", 50),
    ]

    result = compute_rhr_trend(daily)

    # 2 present values (48, 50) -> median 49.0 for both windows.
    assert result["median_7d"] == 49.0
    assert result["median_30d"] == 49.0
    assert result["rhr_trend"] == "stable"


@pytest.mark.unit
def test_rhr_trend_all_missing_returns_none() -> None:
    """No usable RHR -> medians None, trend 'stable' (no signal)."""
    daily = [("2026-06-01", None), ("2026-06-02", None)]

    result = compute_rhr_trend(daily)

    assert result["median_7d"] is None
    assert result["median_30d"] is None
    assert result["rhr_trend"] == "stable"


@pytest.mark.unit
def test_hrv_under_recovery_two_days_below() -> None:
    """Latest 2 nights below baseline_low -> under_recovery, count 2."""
    rows = [
        ("2026-06-20", 62.0, 55.0, 75.0),  # within band
        ("2026-06-21", 50.0, 55.0, 75.0),  # below low
        ("2026-06-22", 48.0, 55.0, 75.0),  # below low (latest)
    ]

    result = compute_hrv_recovery(rows)

    assert result["hrv_below_baseline_days"] == 2
    assert result["under_recovery"] is True
    assert result["latest_ms"] == 48.0
    assert result["status"] == "low"


@pytest.mark.unit
def test_hrv_within_baseline() -> None:
    """Latest night within the baseline band -> not under-recovery, count 0."""
    rows = [
        ("2026-06-21", 50.0, 55.0, 75.0),  # below low (older)
        ("2026-06-22", 64.0, 55.0, 75.0),  # within band (latest)
    ]

    result = compute_hrv_recovery(rows)

    assert result["hrv_below_baseline_days"] == 0
    assert result["under_recovery"] is False
    assert result["latest_ms"] == 64.0
    assert result["status"] == "balanced"
