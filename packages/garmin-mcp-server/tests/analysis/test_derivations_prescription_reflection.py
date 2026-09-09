"""A prescribed session executed as prescribed must read that way (Issue #1086).

Covers the four deterministic halves of the fix: the next-run HR band comes
from the prescription rather than the run's own average, the verdict says which
axes came out on plan, a build-up is detected as its own category, and a day
with several prescribed rows judges the run against the running one.
"""

import pytest

from garmin_mcp.analysis.derivations import (
    compute_next_run_target,
    compute_prescription_verdict,
    detect_progression_session,
    map_phase_category,
    select_prescription_for_run,
)

# Garmin native zones on LTHR 170 (the athlete's live boundaries).
HR_ZONES = {
    "zones": [
        {"zone_number": 1, "low_boundary": 110, "high_boundary": 135},
        {"zone_number": 2, "low_boundary": 136, "high_boundary": 150},
        {"zone_number": 3, "low_boundary": 151, "high_boundary": 161},
        {"zone_number": 4, "low_boundary": 162, "high_boundary": 169},
        {"zone_number": 5, "low_boundary": 170, "high_boundary": 220},
    ]
}

# The 2026-09-09 prescription: a 5km build-up capped at Zone4.
TEMPO_PRESCRIPTION = {
    "session_type": "tempo",
    "title": "単独 5kmビルドアップ（Z2→Z3→低Z4→Z4）",
    "target_km": 8.0,
    "hr_low": 162,
    "hr_high": 169,
    "rationale": "km1-2=Z2 / km3=Z3 / km4=低Z4 / km5=Z4",
}

# Its run-phase splits: HR 142->168 while the pace drops 6:31 -> 5:34.
BUILD_UP_SPLITS = [
    {"avg_heart_rate": 142, "avg_pace_seconds_per_km": 391.3},
    {"avg_heart_rate": 150, "avg_pace_seconds_per_km": 405.0},
    {"avg_heart_rate": 157, "avg_pace_seconds_per_km": 377.1},
    {"avg_heart_rate": 164, "avg_pace_seconds_per_km": 341.8},
    {"avg_heart_rate": 168, "avg_pace_seconds_per_km": 334.1},
]


def _tempo_target(
    hr_zones_detail: dict | None = None,
    prescription: dict | None = None,
) -> dict:
    """The 2026-09-09 tempo run's inputs, varying only the HR-band sources."""
    result: dict = compute_next_run_target(
        training_type="tempo",
        planned_workout=None,
        vo2_max=None,
        # 3.0278 m/s -> 330.3 s/km LT pace.
        lactate_threshold={"speed_mps": 3.0277693},
        avg_hr=148,
        avg_pace_s_per_km=398,
        hr_zones_detail=hr_zones_detail,
        prescription=prescription,
    )
    return result


@pytest.mark.unit
def test_next_run_target_tempo_uses_prescription_hr_band() -> None:
    """The prescribed band wins over the run's warmup-diluted average."""
    result = _tempo_target(hr_zones_detail=HR_ZONES, prescription=TEMPO_PRESCRIPTION)

    assert result["target_hr_low"] == 162
    assert result["target_hr_high"] == 169
    assert result["hr_basis"] == "prescription"


@pytest.mark.unit
def test_next_run_target_tempo_falls_back_to_native_zone_band() -> None:
    """Without a prescription the band spans Garmin's own Zone3 to Zone4."""
    result = _tempo_target(hr_zones_detail=HR_ZONES)

    assert (result["target_hr_low"], result["target_hr_high"]) == (151, 169)
    assert result["hr_basis"] == "garmin_native_zone"


@pytest.mark.unit
def test_next_run_target_tempo_falls_back_to_avg_hr_band() -> None:
    """With neither source the legacy avg_hr +/- 5 band is the last resort."""
    result = _tempo_target()

    assert (result["target_hr_low"], result["target_hr_high"]) == (143, 153)
    assert result["hr_basis"] == "recent_avg_hr"


@pytest.mark.unit
def test_next_run_target_tempo_has_no_scalar_target_hr() -> None:
    """The scalar target_hr (= the run's average) is gone: it read as Zone2."""
    assert "target_hr" not in _tempo_target(prescription=TEMPO_PRESCRIPTION)


@pytest.mark.unit
def test_next_run_target_tempo_emits_reference_pace_range() -> None:
    """Quality sessions get the pace-range keys the web card renders."""
    result = _tempo_target()

    # LT pace 330.3s -> 5:30/km; target = -3s -> 5:27/km (the faster end).
    assert result["reference_pace_low_formatted"] == "5:27/km"
    assert result["reference_pace_high_formatted"] == "5:30/km"


@pytest.mark.unit
def test_next_run_target_easy_emits_reference_pace_range() -> None:
    """The easy family gains the same low/high aliases."""
    result = compute_next_run_target(
        training_type="aerobic_base",
        planned_workout=None,
        vo2_max=None,
        lactate_threshold=None,
        avg_hr=144,
        avg_pace_s_per_km=420,
        hr_zones_detail=HR_ZONES,
    )

    assert result["reference_pace_low_formatted"] == "6:55/km"
    assert result["reference_pace_high_formatted"] == "7:05/km"


@pytest.mark.unit
def test_prescription_verdict_on_plan_lists_all_axes_when_ok() -> None:
    """A ✅ names every on-plan axis and states the tolerance band."""
    result = compute_prescription_verdict(
        TEMPO_PRESCRIPTION,
        {
            "distance_km": 7.14106,
            "duration_min": 47.4,
            "avg_hr": 148,
            "training_type": "tempo",
        },
    )

    assert result is not None
    assert result["verdict"] == "✅"
    assert result["on_plan"] == ["intensity_class", "volume", "hr_ceiling"]
    assert "85-130%" in result["reasons"][0]


@pytest.mark.unit
def test_prescription_verdict_on_plan_excludes_short_volume() -> None:
    """A real shortfall drops volume from on_plan (the other axes stay)."""
    result = compute_prescription_verdict(
        {"session_type": "easy", "title": "イージー 5km", "target_km": 5.0},
        {"distance_km": 3.0, "duration_min": 21.0, "avg_hr": 138},
    )

    assert result is not None
    assert result["verdict"] == "🟡"
    assert "volume" not in result["on_plan"]
    assert "intensity_class" in result["on_plan"]


@pytest.mark.unit
def test_detect_progression_session_true_for_hr_and_pace_ramp() -> None:
    """HR climbing while pace drops is a build-up, prescription or not."""
    assert detect_progression_session(None, BUILD_UP_SPLITS) is True


@pytest.mark.unit
def test_detect_progression_session_false_for_steady_tempo_with_drift() -> None:
    """Cardiac drift at an even pace is not a build-up."""
    steady = [
        {"avg_heart_rate": 155, "avg_pace_seconds_per_km": 330},
        {"avg_heart_rate": 158, "avg_pace_seconds_per_km": 331},
        {"avg_heart_rate": 162, "avg_pace_seconds_per_km": 329},
        {"avg_heart_rate": 166, "avg_pace_seconds_per_km": 332},
        {"avg_heart_rate": 168, "avg_pace_seconds_per_km": 330},
    ]

    assert detect_progression_session(None, steady) is False


@pytest.mark.unit
def test_detect_progression_session_true_for_marked_prescription() -> None:
    """A prescription that names a build-up needs only the HR ramp."""
    held_pace = [
        {"avg_heart_rate": 142, "avg_pace_seconds_per_km": 380},
        {"avg_heart_rate": 152, "avg_pace_seconds_per_km": 381},
        {"avg_heart_rate": 160, "avg_pace_seconds_per_km": 379},
    ]

    assert detect_progression_session(TEMPO_PRESCRIPTION, held_pace) is True


@pytest.mark.unit
def test_detect_progression_session_false_for_two_splits() -> None:
    """Two splits cannot evidence a ramp."""
    assert detect_progression_session(TEMPO_PRESCRIPTION, BUILD_UP_SPLITS[:2]) is False


@pytest.mark.unit
def test_map_phase_category_returns_progression_when_detected() -> None:
    """A detected build-up replaces the steady-tempo criteria."""
    assert map_phase_category("tempo", None, is_progression=True) == "progression"


@pytest.mark.unit
def test_map_phase_category_ignores_progression_for_interval() -> None:
    """Interval structure is work/recovery, never a ramp."""
    assert (
        map_phase_category("interval_training", None, is_progression=True)
        == "interval_sprint"
    )


@pytest.mark.unit
def test_select_prescription_for_run_prefers_running_row() -> None:
    """A 補強 row filed first is not what the run answered."""
    strength = {"prescription_id": 59, "session_type": "strength", "title": "補強 25分"}
    rows = [strength, TEMPO_PRESCRIPTION]

    assert select_prescription_for_run(rows) is TEMPO_PRESCRIPTION


@pytest.mark.unit
def test_select_prescription_for_run_keeps_rest_row() -> None:
    """A rest day still judges the run: running it is the deviation."""
    rest = {"session_type": "rest", "title": "休養"}

    assert select_prescription_for_run([rest]) is rest


@pytest.mark.unit
def test_select_prescription_for_run_none_without_rows() -> None:
    """No prescription, nothing to judge against."""
    assert select_prescription_for_run([]) is None
