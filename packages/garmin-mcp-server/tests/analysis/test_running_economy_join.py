"""Tests for running-economy weight-join helpers (#552).

Pure functions, no I/O. Cover EF computation, nearest-weight matching (within /
outside the window, tie-prefers-past) and the run x weight join (drop unmatched,
sort ascending, EF computed). The integration test asserts the coupled output is
JSON-serialisable across the MCP boundary.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

import pytest

from garmin_mcp.analysis.running_economy import (
    RunRecord,
    WeightMeasurement,
    compute_ef,
    join_runs_with_weight,
    nearest_weight,
)

# --- compute_ef() ---------------------------------------------------------


@pytest.mark.unit
def test_compute_ef_happy_path() -> None:
    """EF = 2.6 / 144.0 ~= 0.018056."""
    result = compute_ef(2.6, 144.0)
    assert result is not None
    # Exact definition speed/HR (rel<1e-6); rounds to the 0.018056 display value.
    assert result == pytest.approx(2.6 / 144.0, rel=1e-6)
    assert round(result, 6) == 0.018056


@pytest.mark.unit
def test_compute_ef_zero_hr_returns_none() -> None:
    """Non-positive HR -> EF undefined -> None."""
    assert compute_ef(2.6, 0.0) is None


# --- nearest_weight() -----------------------------------------------------


@pytest.mark.unit
def test_nearest_weight_within_window() -> None:
    """Nearest within +/-14d wins (78.0kg @ 2d) over a farther measurement."""
    run = date(2025, 6, 10)
    measurements = [
        WeightMeasurement(date(2025, 6, 8), 78.0),
        WeightMeasurement(date(2025, 5, 20), 80.0),
    ]
    assert nearest_weight(run, measurements) == (78.0, 2)


@pytest.mark.unit
def test_nearest_weight_outside_window_returns_none() -> None:
    """Only candidate is 21d away (>14) -> no match."""
    run = date(2025, 6, 10)
    measurements = [WeightMeasurement(date(2025, 5, 20), 80.0)]
    assert nearest_weight(run, measurements) is None


@pytest.mark.unit
def test_nearest_weight_ties_prefer_past() -> None:
    """Equal 3d gaps -> the earlier (past) measurement is preferred."""
    run = date(2025, 6, 10)
    measurements = [
        WeightMeasurement(date(2025, 6, 7), 78.0),
        WeightMeasurement(date(2025, 6, 13), 79.0),
    ]
    assert nearest_weight(run, measurements) == (78.0, 3)


# --- join_runs_with_weight() ----------------------------------------------


@pytest.mark.unit
def test_join_drops_unmatched_runs() -> None:
    """A run with no weight in the window is dropped; the matched one is kept."""
    runs = [
        RunRecord(1, date(2025, 6, 10), 2.6, 144.0),  # matches 2025-06-08
        RunRecord(2, date(2025, 1, 1), 2.5, 140.0),  # no weight nearby
    ]
    measurements = [WeightMeasurement(date(2025, 6, 8), 78.0)]

    result = join_runs_with_weight(runs, measurements)

    assert len(result) == 1
    rec = result[0]
    assert rec.activity_id == 1
    assert rec.weight_kg == 78.0
    assert rec.weight_gap_days == 2
    assert rec.ef == pytest.approx(2.6 / 144.0, rel=1e-9)


@pytest.mark.unit
def test_join_sorted_ascending_and_ef_computed() -> None:
    """Reverse-ordered runs come back run_date ascending with EF per row."""
    measurements = [
        WeightMeasurement(date(2025, 6, 1), 80.0),
        WeightMeasurement(date(2025, 6, 11), 79.0),
        WeightMeasurement(date(2025, 6, 21), 78.0),
    ]
    runs = [
        RunRecord(3, date(2025, 6, 20), 2.7, 150.0),
        RunRecord(2, date(2025, 6, 10), 2.6, 145.0),
        RunRecord(1, date(2025, 6, 2), 2.5, 140.0),
    ]

    result = join_runs_with_weight(runs, measurements)

    assert [r.activity_id for r in result] == [1, 2, 3]
    assert [r.run_date for r in result] == [
        date(2025, 6, 2),
        date(2025, 6, 10),
        date(2025, 6, 20),
    ]
    for r in result:
        assert r.ef == pytest.approx(r.avg_speed_ms / r.avg_heart_rate, rel=1e-9)


# --- integration ----------------------------------------------------------


@pytest.mark.integration
def test_e2e_join_serializable() -> None:
    """Coupled records survive json.dumps (MCP boundary) without raising."""
    runs = [
        RunRecord(101, date(2025, 6, 5), 2.55, 142.0),
        RunRecord(102, date(2025, 6, 15), 2.62, 146.0),
        RunRecord(103, date(2025, 7, 1), 2.70, 150.0),
    ]
    measurements = [
        WeightMeasurement(date(2025, 6, 4), 80.5),
        WeightMeasurement(date(2025, 6, 16), 79.8),
        WeightMeasurement(date(2025, 6, 30), 79.1),
    ]

    result = join_runs_with_weight(runs, measurements)

    serialized = json.dumps([asdict(r) for r in result], default=str)
    assert serialized  # non-empty, no exception
    assert len(result) == 3
