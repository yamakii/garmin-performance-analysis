"""The intensity row reads the run's HR zones, not Garmin's TE label (#1490).

Garmin's ``trainingEffectLabel`` names the run's main benefit: a 2 x 10 min
cruise at 158 bpm came out ``AEROBIC_BASE`` and read as an easy run on a
threshold day, which also dropped its volume from the verdict. The verdict now
compares the zone-refined ``intensity_category``, and a judged step band owns
the intensity of the steps it covers.
"""

import pytest

from garmin_mcp.analysis.derivations import compute_prescription_verdict
from garmin_mcp.analysis.plan_axes import AxisResult

CRUISE = {
    "session_type": "threshold",
    "title": "クルーズ 2×10分（148-158）",
    "target_minutes": 20,
}


def _actual(category: str) -> dict:
    return {
        "duration_min": 35.0,
        "avg_hr": 152,
        "training_type": "aerobic_base",
        "intensity_category": category,
    }


def _band(status: str) -> AxisResult:
    return AxisResult("hr_band", "心拍帯", "148-158 bpm", "-", status, 0, ())  # type: ignore[arg-type]


@pytest.mark.unit
def test_verdict_uses_zone_category_over_te_label() -> None:
    """``moderate`` (Zone 3 dominant) is not compared, whatever the label says."""
    result = compute_prescription_verdict(CRUISE, _actual("moderate"))

    assert result is not None
    assert "intensity_class" in result["on_plan"]
    assert "volume" in result["on_plan"]
    assert result["volume_judged"] is True
    assert result["verdict"] == "✅"


@pytest.mark.unit
def test_verdict_easy_category_on_threshold_day_still_mismatch() -> None:
    """A run whose zones really were easy is still a lower class than prescribed."""
    result = compute_prescription_verdict(CRUISE, _actual("easy"))

    assert result is not None
    assert result["verdict"] == "🟡"
    assert "intensity_class" not in result["on_plan"]
    assert result["volume_judged"] is False
    assert any("強度を下げています" in reason for reason in result["reasons"])


@pytest.mark.unit
def test_verdict_structure_band_axis_owns_intensity() -> None:
    """Warmup and cooldown can make the whole run read easy; the band says otherwise."""
    result = compute_prescription_verdict(
        CRUISE, _actual("easy"), axes=[_band("on_plan")]
    )

    assert result is not None
    assert "intensity_class" in result["on_plan"]
    assert result["intensity_by_steps"] is True
    assert result["volume_judged"] is True
    assert "volume" in result["on_plan"]


@pytest.mark.unit
def test_verdict_insufficient_band_axis_keeps_class_check() -> None:
    """An unjudged band cannot stand in for the class comparison."""
    result = compute_prescription_verdict(
        CRUISE, _actual("easy"), axes=[_band("insufficient")]
    )

    assert result is not None
    assert "intensity_class" not in result["on_plan"]
    assert result["intensity_by_steps"] is False
    assert result["volume_judged"] is False
