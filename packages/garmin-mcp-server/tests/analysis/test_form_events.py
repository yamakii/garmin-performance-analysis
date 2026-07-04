"""Tests for the single-source material form-anomaly event semantics (#809).

Covers the moved helpers (``is_material_severe`` / ``count_material_events``)
and the new ``count_high_severity`` / ``should_flag_run`` flag rule, calibrated
against 90 days of real data (pooled baseline ~2.6 events/hour).
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.form_events import (
    count_high_severity,
    count_material_events,
    is_material_severe,
    should_flag_run,
)


def _anomaly(timestamp: int, metric: str, z: float, cause: str) -> dict[str, Any]:
    """Build a minimal anomaly record for the material-event helpers."""
    return {
        "timestamp": timestamp,
        "metric": metric,
        "z_score": z,
        "probable_cause": cause,
    }


@pytest.mark.unit
def test_count_material_events_dedups_adjacent() -> None:
    """Adjacent per-metric spikes collapse; a far one is a separate event.

    ts=100 (GCT z4), 100 (VO z4), 101 (VR z4) fall within the ±2s dedup window
    -> 1 event; ts=140 (GCT z4) is far away -> a 2nd event. Total 2.
    """
    anomalies = [
        _anomaly(100, "directGroundContactTime", 4.0, "pace_change"),
        _anomaly(100, "directVerticalOscillation", 4.0, "pace_change"),
        _anomaly(101, "directVerticalRatio", 4.0, "pace_change"),
        _anomaly(140, "directGroundContactTime", 4.0, "elevation_change"),
    ]

    assert count_material_events(anomalies) == 2


@pytest.mark.unit
def test_count_material_events_excludes_isolated_and_low() -> None:
    """Isolated noise and sub-3.5 z spikes drop; one material-severe remains.

    isolated z5 (no cause) and pace z3.2 (|z| <= 3.5) are excluded; only the
    elevation z4 survives -> 1 event.
    """
    anomalies = [
        _anomaly(50, "directVerticalOscillation", 5.0, "isolated"),
        _anomaly(200, "directGroundContactTime", 3.2, "pace_change"),
        _anomaly(400, "directVerticalRatio", 4.0, "elevation_change"),
    ]

    assert count_material_events(anomalies) == 1


@pytest.mark.unit
def test_is_material_severe_boundary() -> None:
    """Material cause + |z| > 3.5 is severe; isolated or z <= 3.5 is not."""
    assert is_material_severe(_anomaly(0, "gct", 4.0, "pace_change")) is True
    assert is_material_severe(_anomaly(0, "gct", 5.0, "isolated")) is False
    assert is_material_severe(_anomaly(0, "gct", 3.5, "elevation_change")) is False


@pytest.mark.unit
def test_count_high_severity_material_only() -> None:
    """Only material anomalies with |z| > 4.5 count; isolated high-z is excluded.

    isolated z5.0 -> dropped (isolated); pace z4.8 -> counts (material, > 4.5);
    elevation z4.0 -> dropped (<= 4.5). Total 1.
    """
    anomalies = [
        _anomaly(10, "directGroundContactTime", 5.0, "isolated"),
        _anomaly(20, "directGroundContactTime", 4.8, "pace_change"),
        _anomaly(30, "directVerticalRatio", 4.0, "elevation_change"),
    ]

    assert count_high_severity(anomalies) == 1


@pytest.mark.unit
def test_should_flag_run_requires_min_events() -> None:
    """Below the fixed floor (events=2 < 3) never flags, even if excess-of-baseline."""
    assert should_flag_run(events=2, hours=0.5, baseline_rate=2.6) is False


@pytest.mark.unit
def test_should_flag_run_exceeds_expected() -> None:
    """events=3 over 0.5h at baseline 2.6/h (expected 1.3, 2x=2.6 <= 3) -> flag."""
    assert should_flag_run(events=3, hours=0.5, baseline_rate=2.6) is True


@pytest.mark.unit
def test_should_flag_run_long_run_within_expected() -> None:
    """Real 6/21 case: 4 events over 1.7h at 2.6/h (2x expected 8.84 > 4) -> no flag."""
    assert should_flag_run(events=4, hours=1.7, baseline_rate=2.6) is False


@pytest.mark.unit
def test_should_flag_run_no_baseline_fallback() -> None:
    """With no baseline, fall back to the conservative fixed floor (>= 3 events)."""
    assert should_flag_run(events=3, hours=0.5, baseline_rate=None) is True
    assert should_flag_run(events=2, hours=0.5, baseline_rate=None) is False
