"""Unit tests for deterministic analysis derivations (Issue #671)."""

import pytest

from garmin_mcp.analysis.derivations import (
    compute_next_run_target,
    compute_prescription_verdict,
    compute_vs_previous,
    compute_week_position,
    compute_weighted_star_rating,
    detect_garmin_conflicts,
    map_environment_category,
    map_phase_category,
    summarize_adherence,
    weighted_star_rating_raw,
)


@pytest.mark.unit
def test_compute_weighted_star_rating_basic() -> None:
    rating = compute_weighted_star_rating(
        {"effort": 4.0, "performance": 3.0, "efficiency": 5.0, "execution": 2.0},
        {"effort": 0.4, "performance": 0.3, "efficiency": 0.2, "execution": 0.1},
    )

    assert rating == 3.7


@pytest.mark.unit
def test_weighted_star_rating_raw_no_rounding() -> None:
    # Issue #859: the raw weighted mean must NOT be rounded. This breakdown
    # lands exactly on the 3.15 (X.X5) boundary where compute_weighted_star_rating
    # would round to 3.1 (half-to-even) but the true mean is 3.15.
    raw = weighted_star_rating_raw(
        {"temperature": 2.5, "humidity": 3.0, "terrain": 4.0, "wind": 4.0},
        {"temperature": 0.4, "humidity": 0.25, "terrain": 0.2, "wind": 0.15},
    )

    assert raw == pytest.approx(3.15)
    assert raw != 3.1


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


@pytest.mark.unit
def test_next_run_target_works_without_plan() -> None:
    """With plan vs actual removed (Issue #785), planned_workout is always None.

    The helper must still return a valid target dict driven by training_type.
    """
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=144,
        avg_pace_s_per_km=405,
    )

    assert result["recommended_type"] == "easy"
    assert result["target_hr_low"] == 139
    assert result["target_hr_high"] == 149
    assert "insufficient_data" not in result


# --- easy/recovery target anchored to Garmin native zones (Issue #863) ---

_NATIVE_ZONES = {
    "zones": [
        {"zone_number": 1, "low_boundary": 123, "high_boundary": 139},
        {"zone_number": 2, "low_boundary": 140, "high_boundary": 152},
        {"zone_number": 3, "low_boundary": 153, "high_boundary": 169},
    ]
}


@pytest.mark.unit
def test_easy_target_uses_garmin_zone2_band() -> None:
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=136,
        avg_pace_s_per_km=441,
        hr_zones_detail=_NATIVE_ZONES,
    )

    assert result["recommended_type"] == "easy"
    assert result["target_hr_low"] == 140
    assert result["target_hr_high"] == 152
    assert result["target_zone"] == "Zone2"
    assert result["hr_basis"] == "garmin_native_zone"
    assert result["typical_hr"] == 136


@pytest.mark.unit
def test_recovery_target_uses_zone1_band() -> None:
    result = compute_next_run_target(
        training_type="recovery",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=130,
        avg_pace_s_per_km=460,
        hr_zones_detail=_NATIVE_ZONES,
    )

    assert result["recommended_type"] == "recovery"
    assert result["target_hr_low"] == 123
    assert result["target_hr_high"] == 139
    assert result["target_zone"] == "Zone1"
    assert result["hr_basis"] == "garmin_native_zone"


@pytest.mark.unit
def test_easy_target_falls_back_to_avg_pm5_without_zones() -> None:
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=140,
        avg_pace_s_per_km=405,
        hr_zones_detail=None,
    )

    assert result["target_hr_low"] == 135
    assert result["target_hr_high"] == 145
    assert result["hr_basis"] == "recent_avg_hr"
    assert "target_zone" not in result


@pytest.mark.unit
def test_easy_target_insufficient_when_avg_hr_none() -> None:
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=None,
        avg_pace_s_per_km=405,
        hr_zones_detail=_NATIVE_ZONES,
    )

    assert result["insufficient_data"] is True
    assert result["recommended_type"] == "easy"


@pytest.mark.unit
def test_easy_target_reference_pace_preserved() -> None:
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=136,
        avg_pace_s_per_km=441,
        hr_zones_detail=_NATIVE_ZONES,
    )

    assert result["reference_pace_formatted"] == "7:21/km"
    assert result["reference_pace_fast_formatted"] == "7:16/km"
    assert result["reference_pace_slow_formatted"] == "7:26/km"


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


@pytest.mark.unit
def test_phase_category_works_without_plan() -> None:
    """Plan vs actual removed (Issue #785): planned_workout is always None.

    map_phase_category must still classify from training_type alone.
    """
    assert (
        map_phase_category(training_type="tempo", planned_workout=None)
        == "tempo_threshold"
    )
    assert (
        map_phase_category(training_type="recovery", planned_workout=None)
        == "low_moderate"
    )


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


# --- detect_garmin_conflicts / summarize_adherence (Issue #980) ---


def _ladder_step(week_start: str = "2026-09-07", target_km: float = 25.0) -> dict:
    """A ladder step for the given week (marks the week as having a long run)."""
    return {
        "current": {"week_start": week_start, "target_km": target_km},
        "previous": None,
        "next": None,
    }


@pytest.mark.unit
def test_detect_garmin_conflicts_flags_quality_on_long_day() -> None:
    """A Garmin quality item on the long-run day collides with the ladder step."""
    conflicts = detect_garmin_conflicts(
        [{"date": "2026-09-13", "title": "Threshold"}],
        _ladder_step(),
        1,
        "build",
        "2026-09-07",
    )

    assert conflicts == [
        {
            "date": "2026-09-13",
            "garmin_title": "Threshold",
            "reason": "quality_on_long_day",
        }
    ]


@pytest.mark.unit
def test_detect_garmin_conflicts_flags_second_quality() -> None:
    """With a 1-quality budget, only the *extra* quality item is flagged."""
    conflicts = detect_garmin_conflicts(
        [
            {"date": "2026-09-08", "title": "Tempo"},
            {"date": "2026-09-10", "title": "Threshold"},
        ],
        _ladder_step(),
        1,
        "build",
        "2026-09-07",
    )

    assert conflicts == [
        {
            "date": "2026-09-10",
            "garmin_title": "Threshold",
            "reason": "second_quality_session",
        }
    ]


@pytest.mark.unit
def test_detect_garmin_conflicts_cutback_phase() -> None:
    """Any quality item conflicts while the block is in its cutback phase."""
    conflicts = detect_garmin_conflicts(
        [{"date": "2026-09-16", "title": "Tempo"}],
        _ladder_step(week_start="2026-09-14", target_km=16.0),
        1,
        "cutback",
        "2026-09-14",
    )

    assert conflicts == [
        {
            "date": "2026-09-16",
            "garmin_title": "Tempo",
            "reason": "quality_in_cutback_week",
        }
    ]


@pytest.mark.unit
def test_detect_garmin_conflicts_base_only_is_empty() -> None:
    """Base / easy items never conflict, however many there are."""
    conflicts = detect_garmin_conflicts(
        [
            {"date": "2026-09-08", "title": "Base"},
            {"date": "2026-09-10", "title": "Base"},
            {"date": "2026-09-12", "title": "Base"},
        ],
        _ladder_step(),
        1,
        "build",
        "2026-09-07",
    )

    assert conflicts == []


@pytest.mark.unit
def test_summarize_adherence_counts_statuses() -> None:
    """Resolved statuses are counted; open rows fall into ``pending``."""
    summary = summarize_adherence(
        [
            {"status": "done"},
            {"status": "done"},
            {"status": "replaced"},
            {"status": "prescribed"},
        ]
    )

    assert summary == {
        "prescribed": 4,
        "done": 2,
        "replaced": 1,
        "skipped": 0,
        "pending": 1,
    }


# ---------------------------------------------------------------------------
# Prescription vs actual (Issue #984)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_week_position_long_run_day() -> None:
    """The week's last day is the long-run day (Monday-start week)."""
    position = compute_week_position("2026-09-13", 0, None, None)

    assert position["week_start"] == "2026-09-07"
    assert position["day_index"] == 6
    assert position["is_long_run_day"] is True
    assert position["days_to_long_run"] == 0


@pytest.mark.unit
def test_week_position_two_days_before_long() -> None:
    """Friday sits two days before the Sunday long run."""
    position = compute_week_position("2026-09-11", 0, None, None)

    assert position["day_index"] == 4
    assert position["days_to_long_run"] == 2
    assert position["is_long_run_day"] is False
    assert position["is_day_after_long_run"] is False


@pytest.mark.unit
def test_week_position_cutback_week() -> None:
    """A cutback ladder step marks the whole week as a cutback."""
    ladder = {
        "current": {"week_start": "2026-09-07", "kind": "cutback", "target_km": 14.0},
        "previous": None,
        "next": {"week_start": "2026-09-14", "kind": "build", "target_km": 28.0},
    }

    position = compute_week_position(
        "2026-09-13", 0, ladder, {"phase": "build", "title": "9月ビルド"}
    )

    assert position["cutback_week"] is True
    assert position["block_phase"] == "build"
    assert position["ladder_step"]["next"]["target_km"] == 28.0


@pytest.mark.unit
def test_verdict_green_long_within_tolerance() -> None:
    """A long run at 97% of target under its HR ceiling answers the plan."""
    verdict = compute_prescription_verdict(
        {
            "session_type": "long",
            "title": "ロング 22km",
            "target_km": 22.0,
            "hr_high": 150,
        },
        {
            "distance_km": 21.4,
            "duration_min": 150.0,
            "avg_hr": 146,
            "training_type": "aerobic_base",
        },
    )

    assert verdict is not None
    assert verdict["verdict"] == "✅"
    assert verdict["prescription_title"] == "ロング 22km"
    assert verdict["reasons"]


@pytest.mark.unit
def test_verdict_yellow_volume_short() -> None:
    """17 km against a 22 km prescription is one deviation, stated in percent."""
    verdict = compute_prescription_verdict(
        {"session_type": "long", "title": "ロング 22km", "target_km": 22.0},
        {"distance_km": 17.0, "avg_hr": 144, "training_type": "long_run"},
    )

    assert verdict is not None
    assert verdict["verdict"] == "🟡"
    assert any("77%" in reason for reason in verdict["reasons"])


@pytest.mark.unit
def test_verdict_red_hr_over_ceiling() -> None:
    """13 bpm over the prescribed easy ceiling is a risk-side deviation."""
    verdict = compute_prescription_verdict(
        {"session_type": "easy", "title": "イージー 8km", "hr_high": 150},
        {"distance_km": 8.0, "avg_hr": 163, "training_type": "aerobic_base"},
    )

    assert verdict is not None
    assert verdict["verdict"] == "🔴"
    assert any("163" in reason for reason in verdict["reasons"])


@pytest.mark.unit
def test_verdict_red_rest_day_run() -> None:
    """Running a prescribed rest day is red on its own."""
    verdict = compute_prescription_verdict(
        {"session_type": "rest", "title": "休養"},
        {"distance_km": 6.0, "avg_hr": 138, "training_type": "aerobic_base"},
    )

    assert verdict is not None
    assert verdict["verdict"] == "🔴"
    assert verdict["reasons"][0].startswith("休養処方")


@pytest.mark.unit
def test_verdict_yellow_easy_instead_of_threshold() -> None:
    """Substituting easy for threshold is a downgrade, not a 225% overload."""
    verdict = compute_prescription_verdict(
        {"session_type": "threshold", "title": "閾値 20分", "target_minutes": 20.0},
        {
            "distance_km": 8.0,
            "duration_min": 45.0,
            "avg_hr": 140,
            "training_type": "aerobic_base",
        },
    )

    assert verdict is not None
    assert verdict["verdict"] == "🟡"
    # The volume ratio (225%) must not be reported: the target described a
    # different session.
    assert not any("225" in reason for reason in verdict["reasons"])


@pytest.mark.unit
def test_verdict_none_without_prescription() -> None:
    """An unprescribed day yields no verdict at all."""
    assert (
        compute_prescription_verdict(
            None, {"distance_km": 10.0, "training_type": "aerobic_base"}
        )
        is None
    )


@pytest.mark.unit
def test_vs_previous_deltas() -> None:
    """Deltas read current minus previous, with the gap in days."""
    result = compute_vs_previous(
        {
            "activity_date": "2026-09-13",
            "pace_s_per_km": 430,
            "avg_hr": 142,
            "gct_ms": 262,
            "cadence_spm": 172,
        },
        {
            "activity_id": 987,
            "activity_date": "2026-09-06",
            "pace_s_per_km": 440,
            "avg_hr": 145,
            "gct_ms": 258,
            "cadence_spm": 174,
        },
    )

    assert result is not None
    assert result["pace_s_per_km"]["delta"] == -10
    assert result["avg_hr"]["delta"] == -3
    assert result["gct_ms"]["delta"] == 4
    assert result["cadence_spm"]["delta"] == -2
    assert result["previous_activity_id"] == 987
    assert result["previous_date"] == "2026-09-06"
    assert result["days_ago"] == 7
    # Faster at a lower HR: restated at the previous run's HR it is faster still.
    assert result["pace_at_hr"]["delta"] == -13


@pytest.mark.unit
def test_vs_previous_none() -> None:
    """Without a comparable previous run there is nothing to compare."""
    assert compute_vs_previous({"pace_s_per_km": 430}, None) is None
