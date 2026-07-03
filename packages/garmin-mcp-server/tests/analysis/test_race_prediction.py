"""Unit tests for the deterministic race-time prediction blend (Issue #716).

These pin :func:`predict_race_times` behaviour: VDOT-only fallback, agreeing vs
diverging source blends, the both-missing sentinel, and full key coverage. All
expected times are recomputed from :class:`VDOTCalculator` so the tests stay
deterministic without hard-coded seconds.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.race_prediction import predict_race_times
from garmin_mcp.training_plan.vdot import VDOTCalculator


def _curve(source_distance_km: float, vdot: float) -> dict:
    """Minimal objective fitness curve with one bucket point."""
    return {
        "objective_curve": [
            {
                "date": "2025-06-01",
                "vdot": vdot,
                "source_distance_km": source_distance_km,
            }
        ],
        "garmin_vo2max": [],
        "optimism_gap": None,
    }


@pytest.mark.unit
def test_predict_vdot_only_low_confidence() -> None:
    """VDOT with no curve -> VDOT time verbatim, single source, low confidence."""
    result = predict_race_times(current_vdot=50.0, fitness_curve=None)

    entry = result["race_5k"]
    assert entry["predicted_seconds"] == VDOTCalculator.predict_race_time(50.0, 5.0)
    assert entry["confidence"] == "low"
    assert entry["sources"] == ["vdot"]


@pytest.mark.unit
def test_predict_blend_agreeing_sources_high() -> None:
    """A 10km bucket within ~1% of the VDOT time blends to high confidence."""
    # vdot 49.5 @10km diverges ~0.85% from vdot 50.0 @10km (< 3% threshold).
    curve_vdot = 49.5
    result = predict_race_times(
        current_vdot=50.0, fitness_curve=_curve(10.0, curve_vdot)
    )

    vdot_seconds = VDOTCalculator.predict_race_time(50.0, 10.0)
    curve_seconds = VDOTCalculator.predict_race_time(curve_vdot, 10.0)

    entry = result["race_10k"]
    assert entry["confidence"] == "high"
    assert entry["sources"] == ["vdot", "curve"]
    # Blended value lies strictly between the two source predictions.
    lo, hi = sorted((vdot_seconds, curve_seconds))
    assert lo < entry["predicted_seconds"] < hi


@pytest.mark.unit
def test_predict_blend_disagreeing_sources_medium() -> None:
    """A 10km bucket ~7-8% slower than the VDOT time -> medium confidence."""
    # vdot 46.0 @10km diverges ~7.4% from vdot 50.0 @10km (> 3% threshold).
    curve_vdot = 46.0
    result = predict_race_times(
        current_vdot=50.0, fitness_curve=_curve(10.0, curve_vdot)
    )

    vdot_seconds = VDOTCalculator.predict_race_time(50.0, 10.0)
    curve_seconds = VDOTCalculator.predict_race_time(curve_vdot, 10.0)
    divergence = abs(curve_seconds - vdot_seconds) / vdot_seconds

    entry = result["race_10k"]
    assert divergence > 0.03  # sanity: sources genuinely disagree
    assert entry["confidence"] == "medium"
    assert entry["sources"] == ["vdot", "curve"]


@pytest.mark.unit
def test_predict_insufficient_data() -> None:
    """No VDOT and no curve -> the insufficient_data sentinel."""
    result = predict_race_times(current_vdot=None, fitness_curve=None)
    assert result == {"insufficient_data": True}


@pytest.mark.unit
def test_predict_returns_all_requested_distances() -> None:
    """Default distances yield exactly the four standard readiness keys."""
    result = predict_race_times(current_vdot=50.0, fitness_curve=None)
    assert set(result) == {"race_5k", "race_10k", "half", "full"}
