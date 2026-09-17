"""Unit tests for compute_long_run_recovery_cost (#1218).

The thresholds were set by backtesting every run >= 12 km with wellness
coverage (n=18), so the cases below are the real mornings that drove them: the
two 2026 injury-trigger events must fire, and the normal ladder long runs
(single-morning RHR bump, lone HRV dip) must not.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.recovery_cost import (
    MIN_CRITERIA_TO_FIRE,
    compute_long_run_recovery_cost,
)

_RUN: dict[str, Any] = {
    "activity_id": 20700000001,
    "activity_date": "2025-12-29",
    "distance_km": 28.6,
    "avg_heart_rate": 148,
    "temperature_c": 8.0,
}


def _baseline(rhr: float, hrv: float, days: int = 14) -> list[dict[str, Any]]:
    """A flat baseline window: ``days`` rows at the given RHR / HRV."""
    return [
        {
            "date": f"2025-12-{15 + i:02d}",
            "resting_hr": rhr,
            "hrv_overnight_ms": hrv,
            "training_readiness": 70,
        }
        for i in range(days)
    ]


def _fired(result: dict[str, Any]) -> set[str]:
    return {c["name"] for c in result["criteria"] if c["fired"]}


@pytest.mark.unit
def test_fires_on_2025_12_29_pattern() -> None:
    """28.6 km: RHR 45 -> 48/49, HRV -16 %, readiness 29 -> all three fire."""
    result = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2025-12-30",
            "resting_hr": 48,
            "hrv_overnight_ms": 50.4,  # -16 % vs 60
            "training_readiness": 29,
            "sleep_seconds": 21600,
            "body_battery_low": 12,
        },
        {"date": "2025-12-31", "resting_hr": 49},
        _baseline(45, 60.0),
    )

    assert result["baseline"] == {"rhr_median": 45.0, "hrv_median": 60.0, "n": 14}
    assert result["d1"]["rhr_delta"] == 3.0
    assert result["d1"]["hrv_delta_pct"] == -16.0
    assert result["d1"]["sleep_hours"] == 6.0
    assert result["d2"]["rhr_delta"] == 4.0
    assert _fired(result) == {"rhr_two_day", "readiness", "hrv"}
    assert result["criteria_fired"] == 3
    assert result["cost_flag"] is True
    assert result["insufficient_data"] is False
    assert "RHR +3/+4" in result["reason_ja"]
    assert "Readiness 29" in result["reason_ja"]


@pytest.mark.unit
def test_fires_on_2025_12_14_pattern_two_of_three() -> None:
    """Half marathon: +2.5 bpm on both mornings and readiness 2 already reach
    the two-of-three bar (the -20 % HRV only adds to it)."""
    result = compute_long_run_recovery_cost(
        {**_RUN, "activity_date": "2025-12-14", "distance_km": 21.1},
        {
            "date": "2025-12-15",
            "resting_hr": 47.5,
            "hrv_overnight_ms": 48.0,  # -20 % vs 60
            "training_readiness": 2,
            "sleep_seconds": 18000,
            "body_battery_low": 5,
        },
        {"date": "2025-12-16", "resting_hr": 47.5},
        _baseline(45, 60.0),
    )

    assert result["d1"]["rhr_delta"] == 2.5
    assert {"rhr_two_day", "readiness"} <= _fired(result)
    assert result["criteria_fired"] >= MIN_CRITERIA_TO_FIRE
    assert result["cost_flag"] is True


@pytest.mark.unit
def test_single_morning_rhr_bump_does_not_fire() -> None:
    """2026-07-18: +0 then +4 bpm, readiness 61, HRV -6 % -> nothing fires."""
    result = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2026-07-19",
            "resting_hr": 45,
            "hrv_overnight_ms": 56.4,  # -6 % vs 60
            "training_readiness": 61,
            "sleep_seconds": 25200,
            "body_battery_low": 30,
        },
        {"date": "2026-07-20", "resting_hr": 49},
        _baseline(45, 60.0),
    )

    assert _fired(result) == set()
    assert result["criteria_fired"] == 0
    assert result["cost_flag"] is False
    assert result["insufficient_data"] is False


@pytest.mark.unit
def test_one_criterion_only_does_not_fire() -> None:
    """2026-06-28: HRV -23 % alone, RHR and readiness normal -> no cost flag."""
    result = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2026-06-29",
            "resting_hr": 45,
            "hrv_overnight_ms": 46.2,  # -23 % vs 60
            "training_readiness": 58,
            "sleep_seconds": 24000,
            "body_battery_low": 25,
        },
        {"date": "2026-06-30", "resting_hr": 45},
        _baseline(45, 60.0),
    )

    assert _fired(result) == {"hrv"}
    assert result["criteria_fired"] == 1
    assert result["cost_flag"] is False


@pytest.mark.unit
def test_missing_d2_uses_d1_at_plus_three() -> None:
    """With no d+2 row the RHR criterion needs +3 on d+1; +2.5 is not enough."""
    at_three = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2025-12-30",
            "resting_hr": 48,  # +3.0
            "hrv_overnight_ms": 60.0,
            "training_readiness": 70,
        },
        None,
        _baseline(45, 60.0),
    )
    assert "rhr_two_day" in _fired(at_three)
    assert at_three["d2"] is None
    assert at_three["criteria"][0]["threshold"] == 3.0

    below = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2025-12-30",
            "resting_hr": 47.5,  # +2.5
            "hrv_overnight_ms": 60.0,
            "training_readiness": 70,
        },
        None,
        _baseline(45, 60.0),
    )
    assert _fired(below) == set()


@pytest.mark.unit
def test_insufficient_baseline() -> None:
    """Three non-null baseline rows cannot anchor a median -> no verdict."""
    rows = _baseline(45, 60.0, days=3) + [
        {"date": "2025-12-25", "resting_hr": None, "hrv_overnight_ms": None},
        {"date": "2025-12-26", "resting_hr": None, "hrv_overnight_ms": None},
    ]
    result = compute_long_run_recovery_cost(
        _RUN,
        {
            "date": "2025-12-30",
            "resting_hr": 48,
            "hrv_overnight_ms": 50.4,
            "training_readiness": 29,
        },
        {"date": "2025-12-31", "resting_hr": 49},
        rows,
    )

    assert result["baseline"]["n"] == 3
    assert result["insufficient_data"] is True
    assert result["cost_flag"] is False
    assert "3日分" in result["reason_ja"]


@pytest.mark.unit
def test_missing_d1_row() -> None:
    """A device-off morning after the run leaves nothing to judge."""
    result = compute_long_run_recovery_cost(
        _RUN,
        None,
        {"date": "2025-12-31", "resting_hr": 49},
        _baseline(45, 60.0),
    )

    assert result["d1"] is None
    assert result["insufficient_data"] is True
    assert result["cost_flag"] is False
    assert result["criteria_fired"] == 0
    assert "翌朝のウェルネス記録" in result["reason_ja"]
