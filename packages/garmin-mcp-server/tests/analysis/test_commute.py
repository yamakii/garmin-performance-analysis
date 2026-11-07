"""Tests for the read-time commute guess (#1522)."""

from __future__ import annotations

from datetime import datetime

import pytest

from garmin_mcp.analysis.commute import (
    COMMUTE_MIN_DISPLACEMENT_KM,
    haversine_km,
    infer_commute,
)

# 2026-10-30, 18:40 local. The Issue's Test Plan calls it a Thursday; it is a
# Friday -- a weekday either way, which is all the rule reads.
_THURSDAY_EVENING = datetime(2026, 10, 30, 18, 40)
_START = (35.68, 139.76)


@pytest.mark.unit
def test_infer_commute_weekday_evening_point_to_point() -> None:
    """A weekday evening run ending ~16 km from its start is a commute."""
    assert infer_commute(_THURSDAY_EVENING, _START, (35.80, 139.65)) is True


@pytest.mark.unit
def test_infer_commute_out_and_back_false() -> None:
    """Start and end 0.2 km apart: an out-and-back, not a commute."""
    end = (35.68 + 0.0018, 139.76)
    assert haversine_km(_START, end) == pytest.approx(0.2, abs=0.01)
    assert haversine_km(_START, end) < COMMUTE_MIN_DISPLACEMENT_KM

    assert infer_commute(_THURSDAY_EVENING, _START, end) is False


@pytest.mark.unit
def test_infer_commute_weekend_false() -> None:
    """Sunday 18:00, 10 km apart: weekends are not commutes."""
    sunday = datetime(2026, 11, 1, 18, 0)
    end = (35.68 + 0.09, 139.76)
    assert haversine_km(_START, end) == pytest.approx(10.0, abs=0.1)

    assert infer_commute(sunday, _START, end) is False


@pytest.mark.unit
def test_infer_commute_missing_gps_false() -> None:
    """No last GPS fix: nothing to read, so no commute."""
    assert infer_commute(_THURSDAY_EVENING, _START, None) is False


@pytest.mark.unit
def test_infer_commute_morning_false() -> None:
    """A weekday run before 17:00 is not an evening commute home."""
    morning = datetime(2026, 10, 30, 7, 30)
    assert infer_commute(morning, _START, (35.80, 139.65)) is False
