"""Recovery-trend analysis (pure functions, no I/O).

Derives resting-heart-rate (RHR) and heart-rate-variability (HRV) recovery
signals from daily wellness rows. These helpers are the analytic core behind
``GarminDBReader.get_recovery_trend`` and the MCP ``get_recovery_trend`` tool
(#499).

The goal is to back the subjective "my cardio came back" with objective markers:
a falling 7-day RHR median vs the 30-day median signals aerobic improvement,
while consecutive nights of HRV below baseline flag under-recovery (combine with
``get_acwr`` high load to catch over-training).

All functions are null-safe: missing days / values are skipped rather than
raising, so device-off days do not break the trend.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

# RHR trend thresholds (bpm, 7-day median minus 30-day median).
RHR_IMPROVING_DELTA = -2  # 7d at least 2 bpm below 30d -> aerobic improvement.
RHR_FATIGUED_DELTA = 3  # 7d at least 3 bpm above 30d -> fatigue / illness.

# HRV under-recovery: this many consecutive nights below baseline_low triggers.
HRV_UNDER_RECOVERY_DAYS = 2


def _median_or_none(values: Sequence[float]) -> float | None:
    """Median of ``values``, or ``None`` when empty (null-safe)."""
    if not values:
        return None
    return round(statistics.median(values), 1)


def compute_rhr_trend(
    daily_rhr: Sequence[tuple[str, int | None]],
) -> dict[str, Any]:
    """Resting-HR trend from a date-ascending daily series.

    Args:
        daily_rhr: ``[(date_str, resting_hr), ...]`` in ascending date order.
            ``resting_hr`` may be ``None`` (device-off day) and is skipped.

    The 7-day median uses the most recent 7 days with data; the 30-day median
    uses the most recent 30. ``rhr_trend`` is derived from ``median_7d -
    median_30d``:

    - ``<= -2`` -> ``"improving"`` (cardio recovered)
    - ``>= +3`` -> ``"fatigued"`` (fatigue / illness)
    - otherwise -> ``"stable"``

    Returns:
        ``{"median_7d", "median_30d", "rhr_trend"}``. Medians are ``None`` when
        no data is available in the window; ``rhr_trend`` is ``"stable"`` when
        either median is ``None`` (insufficient data -> no signal).
    """
    present = [(d, hr) for d, hr in daily_rhr if hr is not None]

    recent_7 = [hr for _, hr in present[-7:]]
    recent_30 = [hr for _, hr in present[-30:]]

    median_7d = _median_or_none(recent_7)
    median_30d = _median_or_none(recent_30)

    rhr_trend = "stable"
    if median_7d is not None and median_30d is not None:
        delta = median_7d - median_30d
        if delta <= RHR_IMPROVING_DELTA:
            rhr_trend = "improving"
        elif delta >= RHR_FATIGUED_DELTA:
            rhr_trend = "fatigued"

    return {
        "median_7d": median_7d,
        "median_30d": median_30d,
        "rhr_trend": rhr_trend,
    }


def compute_hrv_recovery(
    rows: Sequence[tuple[str, float | None, float | None, float | None]],
) -> dict[str, Any]:
    """HRV recovery status from a date-ascending daily series.

    Args:
        rows: ``[(date_str, hrv_overnight_ms, hrv_baseline_low,
            hrv_baseline_high), ...]`` in ascending date order. Any value may be
            ``None`` (missing night) and is treated as no signal.

    Counts how many of the most recent consecutive nights have
    ``hrv_overnight_ms`` below ``hrv_baseline_low``. The count stops at the first
    night that is within (or above) baseline, or that lacks data. ``2`` or more
    consecutive nights below baseline sets ``under_recovery=True``.

    Returns:
        ``{"latest_ms", "status", "hrv_below_baseline_days", "under_recovery"}``.
        ``latest_ms`` / ``status`` describe the most recent night with an HRV
        reading (``None`` when none exist; ``status`` is derived from the
        baseline band: ``"low"`` / ``"balanced"`` / ``"high"``).
    """
    below_days = 0
    for _, ms, low, _high in reversed(rows):
        if ms is None or low is None:
            break
        if ms < low:
            below_days += 1
        else:
            break

    latest_ms: float | None = None
    status: str | None = None
    for _, ms, low, high in reversed(rows):
        if ms is None:
            continue
        latest_ms = ms
        if low is not None and ms < low:
            status = "low"
        elif high is not None and ms > high:
            status = "high"
        elif low is not None or high is not None:
            status = "balanced"
        break

    return {
        "latest_ms": latest_ms,
        "status": status,
        "hrv_below_baseline_days": below_days,
        "under_recovery": below_days >= HRV_UNDER_RECOVERY_DAYS,
    }
