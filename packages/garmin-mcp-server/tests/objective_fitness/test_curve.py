"""Unit tests for the rolling trailing-window max fitness curve (pure logic)."""

import pytest

from garmin_mcp.objective_fitness.curve import FitnessPoint, rolling_max_curve


@pytest.mark.unit
def test_rolling_max_curve_basic() -> None:
    per_run_vdot = [
        ("2026-01-01", 30.0, 5.0),
        ("2026-01-11", 32.0, 5.0),
        ("2026-01-21", 31.0, 5.0),
    ]

    curve = rolling_max_curve(per_run_vdot, window_days=90)

    assert [p.date for p in curve] == ["2026-01-01", "2026-01-11", "2026-01-21"]
    # 3rd point holds the prior peak of 32 (still inside the 90-day window).
    assert [p.vdot for p in curve] == [30.0, 32.0, 32.0]


@pytest.mark.unit
def test_rolling_max_curve_window_drop() -> None:
    per_run_vdot = [
        ("2026-01-01", 35.0, 2.0),
        ("2026-05-01", 30.0, 5.0),
    ]

    curve = rolling_max_curve(per_run_vdot, window_days=90)

    # 2026-01-01 (peak 35) is >90 days before 2026-05-01, so it drops out.
    second = curve[1]
    assert second.date == "2026-05-01"
    assert second.vdot == 30.0
    assert second.source_distance_km == 5.0


@pytest.mark.unit
def test_rolling_max_curve_unsorted_input() -> None:
    ordered = [
        ("2026-01-01", 30.0, 5.0),
        ("2026-01-11", 32.0, 5.0),
        ("2026-01-21", 31.0, 5.0),
    ]
    reversed_input = list(reversed(ordered))

    curve = rolling_max_curve(reversed_input, window_days=90)

    assert curve == [
        FitnessPoint(date="2026-01-01", vdot=30.0, source_distance_km=5.0),
        FitnessPoint(date="2026-01-11", vdot=32.0, source_distance_km=5.0),
        FitnessPoint(date="2026-01-21", vdot=32.0, source_distance_km=5.0),
    ]


@pytest.mark.unit
def test_rolling_max_curve_empty() -> None:
    assert rolling_max_curve([], window_days=90) == []


@pytest.mark.unit
def test_rolling_max_curve_window_boundary() -> None:
    # The earlier point is exactly 90 days before the later one (inclusive).
    per_run_vdot = [
        ("2026-01-01", 40.0, 10.0),
        ("2026-04-01", 30.0, 5.0),  # 2026-01-01 + 90 days == 2026-04-01
    ]

    curve = rolling_max_curve(per_run_vdot, window_days=90)

    later = curve[1]
    assert later.date == "2026-04-01"
    # Boundary is inclusive, so the 40.0 peak is still counted.
    assert later.vdot == 40.0
    assert later.source_distance_km == 10.0
