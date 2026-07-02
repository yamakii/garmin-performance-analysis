"""Unit tests for deterministic analysis derivations (Issue #671)."""

import pytest

from garmin_mcp.analysis.derivations import (
    compute_next_run_target,
    compute_plan_achievement,
    compute_weighted_star_rating,
    map_environment_category,
    map_phase_category,
)


@pytest.mark.unit
def test_compute_weighted_star_rating_basic() -> None:
    rating = compute_weighted_star_rating(
        {"effort": 4.0, "performance": 3.0, "efficiency": 5.0, "execution": 2.0},
        {"effort": 0.4, "performance": 0.3, "efficiency": 0.2, "execution": 0.1},
    )

    assert rating == 3.7


@pytest.mark.unit
def test_compute_weighted_star_rating_clamps_to_5() -> None:
    rating = compute_weighted_star_rating(
        {"effort": 5.5, "performance": 5.5, "efficiency": 5.5, "execution": 5.5},
        {"effort": 0.4, "performance": 0.3, "efficiency": 0.2, "execution": 0.1},
    )

    assert rating == 5.0


@pytest.mark.unit
def test_compute_weighted_star_rating_key_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="weights keys must match"):
        compute_weighted_star_rating(
            {"effort": 4.0, "performance": 3.0, "efficiency": 5.0, "execution": 2.0},
            {"effort": 0.4, "performance": 0.3, "efficiency": 0.3},
        )


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


# --- compute_next_run_target (Issue #672) ---


@pytest.mark.unit
def test_next_target_interval_from_vo2max() -> None:
    result = compute_next_run_target(
        training_type="interval",
        planned_workout=None,
        vo2_max={"precise_value": 52.5},
        lactate_threshold=None,
        avg_hr=160,
        avg_pace_s_per_km=260,
    )

    # 52.5 / 3.5 = 15.0 km/h -> 3600/15.0 = 240s = 4:00 (100% vVO2max).
    assert result["recommended_type"] == "interval"
    assert result["target_pace_fast_formatted"] == "4:00/km"
    # 95% -> 15.0 * 0.95 = 14.25 km/h -> 3600/14.25 = 252.6s -> 4:13.
    assert result["target_pace_slow_formatted"] == "4:13/km"
    assert "insufficient_data" not in result


@pytest.mark.unit
def test_next_target_tempo_from_lt() -> None:
    result = compute_next_run_target(
        training_type="tempo",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold={"speed_mps": 3.333},
        avg_hr=158,
        avg_pace_s_per_km=305,
    )

    # 1000 / 3.333 = 300.03s/km LT pace; target = -3s -> 297s = 4:57.
    assert result["recommended_type"] == "tempo"
    assert result["target_pace_formatted"] == "4:57/km"
    assert result["target_hr"] == 158
    assert "insufficient_data" not in result


@pytest.mark.unit
def test_next_target_easy_hr_based() -> None:
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=144,
        avg_pace_s_per_km=405,
    )

    assert result["recommended_type"] == "easy"
    assert "target_hr_low" in result
    assert "target_hr_high" in result
    assert result["reference_pace_formatted"] == "6:45/km"
    assert "insufficient_data" not in result


@pytest.mark.unit
def test_next_target_insufficient_data() -> None:
    result = compute_next_run_target(
        training_type="interval",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=160,
        avg_pace_s_per_km=260,
    )

    assert result["insufficient_data"] is True
    assert isinstance(result["summary_ja"], str)
    assert result["recommended_type"] == "interval"


# --- map_phase_category (Issue #673) ---


@pytest.mark.unit
def test_phase_category_from_planned_workout() -> None:
    # planned_workout.workout_type takes precedence over training_type.
    result = map_phase_category(
        training_type="aerobic_base",
        planned_workout={"workout_type": "tempo_run"},
    )
    assert result == "tempo_threshold"


@pytest.mark.unit
def test_phase_category_fallback_training_type() -> None:
    result = map_phase_category(training_type="aerobic_base", planned_workout=None)
    assert result == "low_moderate"


@pytest.mark.unit
def test_phase_category_interval() -> None:
    result = map_phase_category(training_type="vo2max", planned_workout=None)
    assert result == "interval_sprint"


@pytest.mark.unit
def test_phase_category_null_default() -> None:
    result = map_phase_category(training_type=None, planned_workout=None)
    assert result == "tempo_threshold"


# --- map_environment_category (Issue #673) ---


@pytest.mark.unit
def test_env_category_recovery() -> None:
    assert map_environment_category("recovery") == "recovery"


@pytest.mark.unit
def test_env_category_base() -> None:
    assert map_environment_category("aerobic_base") == "base_moderate"


@pytest.mark.unit
def test_env_category_tempo() -> None:
    assert map_environment_category("tempo") == "tempo_threshold"


@pytest.mark.unit
def test_env_category_interval() -> None:
    assert map_environment_category("interval") == "interval_sprint"
