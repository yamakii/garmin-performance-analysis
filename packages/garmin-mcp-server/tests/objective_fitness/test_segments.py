"""Tests for best contiguous segment extraction + performance VDOT."""

import pytest

from garmin_mcp.objective_fitness.segments import (
    BestEffort,
    best_contiguous_segment,
    performance_vdot,
    run_best_efforts,
)


def _splits(durations: list[float], distance_m: float = 1000.0) -> list[dict]:
    """Build per-split dicts with equal distances and given durations."""
    return [
        {"distance": distance_m, "duration_seconds": d, "split_index": i}
        for i, d in enumerate(durations)
    ]


@pytest.mark.unit
class TestBestContiguousSegment:
    def test_best_contiguous_segment_happy_path(self):
        splits = _splits([300, 290, 280, 310, 320])
        effort = best_contiguous_segment(splits, target_distance_km=2.0)
        assert effort is not None
        assert isinstance(effort, BestEffort)
        assert effort.target_distance_km == 2.0
        assert effort.actual_distance_km == pytest.approx(2.0)
        assert effort.duration_seconds == pytest.approx(570.0)
        assert effort.pace_seconds_per_km == pytest.approx(285.0)

    def test_best_contiguous_segment_too_short(self):
        splits = _splits([300])
        assert best_contiguous_segment(splits, target_distance_km=5.0) is None

    def test_best_contiguous_segment_window_distance_floor(self):
        # 6 splits of 0.95km each, equal pace; target 2.0km needs 3 splits
        # (2.85km >= 2.0), and the window is minimized (not 4+ splits).
        splits = _splits([285, 285, 285, 285, 285, 285], distance_m=950.0)
        effort = best_contiguous_segment(splits, target_distance_km=2.0)
        assert effort is not None
        assert effort.actual_distance_km == pytest.approx(2.85)
        assert effort.duration_seconds == pytest.approx(855.0)


@pytest.mark.unit
class TestPerformanceVdot:
    def test_performance_vdot_5k(self):
        vdot = performance_vdot(5.0, 1740)
        assert 32.0 <= vdot <= 34.5

    def test_performance_vdot_2k(self):
        vdot = performance_vdot(2.0, 600)
        assert 34.5 <= vdot <= 37.5

    def test_performance_vdot_10k(self):
        vdot = performance_vdot(10.0, 3300)
        assert 35.5 <= vdot <= 38.5


@pytest.mark.unit
class TestRunBestEfforts:
    def test_run_best_efforts_buckets(self):
        splits = _splits([300] * 10)
        efforts = run_best_efforts(splits)
        assert len(efforts) == 3
        assert [e.target_distance_km for e in efforts] == [2.0, 5.0, 10.0]
        for effort in efforts:
            assert 20.0 <= effort.vdot <= 45.0

    def test_run_best_efforts_partial_coverage(self):
        splits = _splits([300] * 6)
        efforts = run_best_efforts(splits)
        assert [e.target_distance_km for e in efforts] == [2.0, 5.0]
