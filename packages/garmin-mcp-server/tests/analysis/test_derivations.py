"""Unit tests for deterministic analysis derivations (Issue #671)."""

import pytest

from garmin_mcp.analysis.derivations import compute_plan_achievement

_EASY_PLAN = {
    "workout_type": "easy",
    "description_ja": "イージーラン",
    "target_hr_low": 120,
    "target_hr_high": 145,
    "target_pace_low": 390,
    "target_pace_high": 420,
}


@pytest.mark.unit
def test_plan_achievement_hr_and_pace_achieved() -> None:
    result = compute_plan_achievement(
        _EASY_PLAN, actual_avg_hr=142, actual_avg_pace_s_per_km=405
    )

    assert result is not None
    assert result["hr_achieved"] is True
    assert result["pace_achieved"] is True
    assert result["targets"]["hr"] == "120-145bpm"
    assert result["actuals"]["pace"] == "6:45/km"
    assert result["description_ja"] == "イージーラン"


@pytest.mark.unit
def test_plan_achievement_pace_missed() -> None:
    result = compute_plan_achievement(
        _EASY_PLAN, actual_avg_hr=142, actual_avg_pace_s_per_km=360
    )

    assert result is not None
    assert result["pace_achieved"] is False
    assert result["hr_achieved"] is True


@pytest.mark.unit
def test_plan_achievement_none_when_no_plan() -> None:
    assert (
        compute_plan_achievement(None, actual_avg_hr=142, actual_avg_pace_s_per_km=405)
        is None
    )


@pytest.mark.unit
def test_plan_achievement_description_ja_fallback() -> None:
    plan = {
        "workout_type": "tempo",
        "description_ja": None,
        "target_hr_low": 150,
        "target_hr_high": 165,
        "target_pace_low": 300,
        "target_pace_high": 320,
    }
    result = compute_plan_achievement(
        plan, actual_avg_hr=158, actual_avg_pace_s_per_km=310
    )

    assert result is not None
    assert result["description_ja"] == "テンポ走"


@pytest.mark.unit
def test_plan_achievement_null_hr_target() -> None:
    plan = {
        "workout_type": "easy",
        "description_ja": "イージーラン",
        "target_hr_low": None,
        "target_hr_high": None,
        "target_pace_low": 390,
        "target_pace_high": 420,
    }
    result = compute_plan_achievement(
        plan, actual_avg_hr=142, actual_avg_pace_s_per_km=405
    )

    assert result is not None
    assert result["hr_achieved"] is None
    assert result["pace_achieved"] is True
    # No HR target -> no formatted hr target string.
    assert "hr" not in result["targets"]
