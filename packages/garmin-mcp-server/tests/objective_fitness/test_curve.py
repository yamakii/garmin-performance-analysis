"""Unit tests for the rolling trailing-window max fitness curve (pure logic)."""

import pytest

from garmin_mcp.objective_fitness.curve import FitnessPoint, rolling_max_curve
from garmin_mcp.objective_fitness.segments import performance_vdot


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


# --- Golden regression tests (Issue #624) -------------------------------------
# These freeze known synthetic inputs -> known outputs so that a silent ~5-10%
# drift in the best-segment VDOT pipeline (Daniels VDOT -> rolling-window max)
# is caught in CI rather than slipping through unnoticed.


@pytest.mark.unit
def test_curve_vdot_golden_5k_2500() -> None:
    # Single 5km effort run at exactly 25:00 (5:00/km). Daniels performance VDOT
    # for 5km/25:00 is ~38.3; a single-day curve point must surface that value.
    best_5k_vdot = performance_vdot(5.0, 1500)
    per_run_vdot = [("2026-01-01", best_5k_vdot, 5.0)]

    curve = rolling_max_curve(per_run_vdot, window_days=90)

    assert len(curve) == 1
    # Daniels sanity: 5km / 25:00 -> ~38.3.
    assert curve[0].vdot == pytest.approx(38.3, abs=0.5)
    # Frozen golden of the current implementation output.
    assert curve[0].vdot == pytest.approx(38.3094, rel=1e-3)
    assert curve[0].source_distance_km == 5.0


@pytest.mark.unit
def test_curve_rolling_max_golden() -> None:
    # A known synthetic 5km best-effort series across three run days. Each run's
    # VDOT is derived from the Daniels model, then fed through the trailing-window
    # max. The resulting series is frozen as a golden to detect drift.
    runs = [
        ("2026-01-01", 5.0, 1560.0),  # 5:12/km
        ("2026-02-01", 5.0, 1500.0),  # 5:00/km (peak)
        ("2026-03-01", 5.0, 1620.0),  # 5:24/km (window still holds the peak)
    ]
    per_run_vdot = [
        (run_date, performance_vdot(dist_km, dur_s), dist_km)
        for run_date, dist_km, dur_s in runs
    ]

    curve = rolling_max_curve(per_run_vdot, window_days=90)

    assert [p.date for p in curve] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    # Frozen golden VDOT series (rolling trailing-window max).
    golden_vdot = [36.568331, 38.309363, 38.309363]
    assert [p.vdot for p in curve] == pytest.approx(golden_vdot, rel=1e-3)
    # The 3rd day holds the Feb peak (still inside the 90-day window).
    assert curve[2].vdot == pytest.approx(curve[1].vdot, rel=1e-9)
