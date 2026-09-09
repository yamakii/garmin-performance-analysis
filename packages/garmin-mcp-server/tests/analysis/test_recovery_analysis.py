"""Unit tests for recovery analysis helpers (#499).

Pure functions only -- no I/O. Cover the RHR 7d/30d-median trend
(improving / fatigued / stable / insufficient data) and the HRV
below-baseline under-recovery counter.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.recovery import (
    classify_recovery_status,
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
def test_recovery_trend_median_golden() -> None:
    """Golden: a 30-day RHR/HRV series freezes the 7d/30d medians + latest HRV.

    The RHR series is 30 distinct ascending values (40..69), so the medians are
    sensitive to both the window slicing (last 7 vs last 30) and the even-count
    midpoint average. The HRV series freezes the most-recent-night reading and
    the consecutive-below-baseline counter. Recompute deliberately if the median
    windows or HRV counting are intentionally changed.
    """
    # 30 days: RHR 40, 41, ... 69 (ascending).
    daily_rhr = [(f"2026-05-{i + 1:02d}", 40 + i) for i in range(30)]

    rhr = compute_rhr_trend(daily_rhr)

    # Last 7 values are 63..69 -> median 66; all 30 (40..69) -> midpoint 54.5.
    assert rhr["median_7d"] == 66
    assert rhr["median_30d"] == pytest.approx(54.5, abs=1e-6)
    assert rhr["rhr_trend"] == "fatigued"

    hrv_rows = [
        ("2026-06-20", 60.0, 55.0, 75.0),  # within band
        ("2026-06-21", 52.0, 55.0, 75.0),  # below low
        ("2026-06-22", 51.5, 55.0, 75.0),  # below low (latest)
    ]

    hrv = compute_hrv_recovery(hrv_rows)

    assert hrv["latest_ms"] == pytest.approx(51.5, abs=1e-6)
    assert hrv["hrv_below_baseline_days"] == 2
    assert hrv["under_recovery"] is True
    assert hrv["status"] == "low"


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


@pytest.mark.unit
def test_status_rest_low_readiness() -> None:
    """Low Training Readiness -> rest/easy (under-recovered)."""
    result = classify_recovery_status(
        readiness=40,
        body_battery_high=70,
        sleep_score=80,
        under_recovery=False,
    )

    assert result["recommendation"] in {"rest", "easy"}
    assert result["reasons"]


@pytest.mark.unit
def test_status_quality_green() -> None:
    """High readiness + good sleep + normal HRV -> quality (T allowed)."""
    result = classify_recovery_status(
        readiness=82,
        body_battery_high=90,
        sleep_score=85,
        under_recovery=False,
    )

    assert result["recommendation"] == "quality"


@pytest.mark.unit
def test_status_moderate_midband() -> None:
    """Mid-band readiness, no flags -> moderate."""
    result = classify_recovery_status(
        readiness=62,
        body_battery_high=75,
        sleep_score=70,
        under_recovery=False,
    )

    assert result["recommendation"] == "moderate"


@pytest.mark.unit
def test_status_under_recovery_overrides() -> None:
    """HRV under-recovery overrides high readiness -> not quality."""
    result = classify_recovery_status(
        readiness=80,
        body_battery_high=85,
        sleep_score=80,
        under_recovery=True,
    )

    assert result["recommendation"] != "quality"
    assert result["recommendation"] in {"rest", "easy"}


@pytest.mark.unit
def test_status_unknown_on_missing_data() -> None:
    """All markers None (device off) -> unknown + non-empty reasons."""
    result = classify_recovery_status(
        readiness=None,
        body_battery_high=None,
        sleep_score=None,
        under_recovery=None,
    )

    assert result["recommendation"] == "unknown"
    assert result["reasons"]
    assert result["score"] is None
