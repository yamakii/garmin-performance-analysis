"""The prescription's purpose is an axis of the plan verdict (Issue #1353).

With a prescription the purpose is the prescription's, so "on plan" includes
having delivered it: a long run that held its effort is on plan on
``continuity``, one that came apart is a 🟡 deviation however well its volume,
intensity and HR ceiling read.
"""

import pytest

from garmin_mcp.analysis.derivations import compute_prescription_verdict
from garmin_mcp.analysis.purpose_outcome import Outcome

LONG_PRESCRIPTION = {
    "session_type": "long",
    "title": "ロング 26km",
    "target_km": 26.0,
    "hr_high": 150,
}

# 26 km at an easy class under the ceiling: every physical axis on plan.
LONG_ACTUAL = {
    "distance_km": 26.1,
    "duration_min": 190.0,
    "avg_hr": 140,
    "training_type": "aerobic_base",
}

HELD = Outcome(
    met=True,
    sustained_share=0.97,
    breakdown_from_km=None,
    sustained_pace_s_per_km=460.0,
    reason="held",
)

CAME_APART = Outcome(
    met=False,
    sustained_share=0.62,
    breakdown_from_km=18.0,
    sustained_pace_s_per_km=470.0,
    reason="came apart",
)


@pytest.mark.unit
def test_verdict_continuity_on_plan_when_held() -> None:
    """A run that held its effort is on plan on continuity and stays ✅."""
    result = compute_prescription_verdict(LONG_PRESCRIPTION, LONG_ACTUAL, outcome=HELD)

    assert result is not None
    assert result["verdict"] == "✅"
    assert result["on_plan"] == [
        "intensity_class",
        "volume",
        "hr_ceiling",
        "continuity",
    ]


@pytest.mark.unit
def test_verdict_continuity_off_plan_on_breakdown() -> None:
    """Volume, intensity and ceiling on plan cannot hide a collapse."""
    result = compute_prescription_verdict(
        LONG_PRESCRIPTION, LONG_ACTUAL, outcome=CAME_APART
    )

    assert result is not None
    assert result["verdict"] == "🟡"
    assert "continuity" not in result["on_plan"]
    assert result["on_plan"] == ["intensity_class", "volume", "hr_ceiling"]
    assert any("18 km から" in reason for reason in result["reasons"])


@pytest.mark.unit
def test_verdict_no_continuity_without_outcome() -> None:
    """A purpose the outcome does not judge adds no axis; the verdict is as before."""
    prescription = {"session_type": "threshold", "title": "閾値走", "hr_high": 165}
    actual = {
        "distance_km": 8.0,
        "duration_min": 45.0,
        "avg_hr": 160,
        "training_type": "threshold",
    }

    with_none = compute_prescription_verdict(prescription, actual, outcome=None)
    without = compute_prescription_verdict(prescription, actual)

    assert with_none == without
    assert with_none is not None
    assert "continuity" not in with_none["on_plan"]


@pytest.mark.unit
def test_verdict_rest_ignores_outcome() -> None:
    """A rest day is judged on resting, whatever an outcome says."""
    rest = {"session_type": "rest", "title": "休養"}
    none_run = {"distance_km": 0, "duration_min": 0}

    result = compute_prescription_verdict(rest, none_run, outcome=CAME_APART)

    assert result is not None
    assert result["verdict"] == "✅"
    assert result["on_plan"] == ["rest"]
