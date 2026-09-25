"""Tests for the workout catalog (Issue #1403)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.run_purpose import PURPOSES
from garmin_mcp.analysis.workout_catalog import TEMPLATES, expand
from garmin_mcp.analysis.workout_structure import (
    registrable_steps,
    structure_totals,
    validate_structure,
)

_TEMPLATE_IDS = sorted(TEMPLATES)


@pytest.mark.unit
@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_catalog_every_template_validates(template_id: str) -> None:
    structure, title = expand(template_id, TEMPLATES[template_id].example)
    assert validate_structure(structure, title=title) is structure
    assert title
    # The registered form is buildable too (judge-only keys stripped).
    assert registrable_steps(structure)


@pytest.mark.unit
@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_catalog_purpose_allowed_for_session_types(template_id: str) -> None:
    template = TEMPLATES[template_id]
    assert template.session_types
    purpose = PURPOSES[template.default_purpose]
    assert template.session_types <= purpose.session_types


@pytest.mark.unit
def test_cruise_4x5_structure_and_title() -> None:
    structure, title = expand(
        "cruise_intervals",
        {
            "reps": 4,
            "work_minutes": 5,
            "recovery_minutes": 3,
            "hr_low": 162,
            "hr_high": 169,
            "warmup_minutes": 10,
            "cooldown_minutes": 5,
        },
    )
    expected: list[dict[str, Any]] = [
        {"step_type": "warmup", "duration_minutes": 10},
        {
            "repeat_count": 4,
            "steps": [
                {
                    "step_type": "run",
                    "duration_minutes": 5,
                    "hr_low": 162,
                    "hr_high": 169,
                },
                {"step_type": "recovery", "duration_minutes": 3},
            ],
        },
        {"step_type": "cooldown", "duration_minutes": 5},
    ]
    assert structure == expected
    assert title == "クルーズ 4×5分（162-169）／3分ジョグ"


@pytest.mark.unit
def test_progression_rejects_descending_bands() -> None:
    with pytest.raises(ValueError, match="does not ascend"):
        expand(
            "progression",
            {
                "stages": [
                    {"minutes": 10, "hr_low": 151, "hr_high": 161},
                    {"minutes": 10, "hr_low": 136, "hr_high": 150},
                ]
            },
        )


@pytest.mark.unit
def test_long_with_mp_totals() -> None:
    structure, title = expand(
        "long_with_mp",
        {
            "easy_km_before": 10,
            "mp_km": 8,
            "easy_km_after": 2,
            "hr_high_easy": 150,
            "mp_pace_low": 365,
            "mp_pace_high": 370,
            "mp_hr_high": 162,
        },
    )
    seconds, km = structure_totals(structure)
    assert seconds is None
    assert km == pytest.approx(20.0)
    assert title == "ロング 20km（うちMP 8km 6:05-6:10）"


@pytest.mark.unit
def test_race_optional_finish_is_optional_step() -> None:
    structure, _title = expand(
        "race",
        {
            "distance_km": 21.1,
            "hr_high": 165,
            "optional_finish": {"km": 4, "pace_low": 365, "pace_high": 370},
        },
    )
    last = structure[-1]
    assert last.get("optional") is True
    assert last.get("distance_m") == 4000
    assert last.get("pace_low_s_per_km") == 365
    assert last.get("pace_high_s_per_km") == 370
    # The optional finish is not registered on the watch.
    assert all(not s.get("optional") for s in registrable_steps(structure))


@pytest.mark.unit
def test_expand_unknown_template() -> None:
    with pytest.raises(ValueError, match="unknown workout template"):
        expand("foo", {})


@pytest.mark.unit
def test_expand_rejects_unknown_params() -> None:
    with pytest.raises(ValueError, match="unknown params"):
        expand("easy", {"minutes": 45, "hr_high": 150, "pace": 400})


@pytest.mark.unit
def test_expand_rejects_both_minutes_and_km() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        expand("easy", {"minutes": 45, "km": 8, "hr_high": 150})


@pytest.mark.unit
def test_short_reps_work_seconds_bounds() -> None:
    with pytest.raises(ValueError, match="work_seconds"):
        expand("short_reps", {"reps": 10, "work_seconds": 60, "recovery_seconds": 60})


@pytest.mark.unit
def test_easy_strides_sums_to_total_minutes() -> None:
    structure, title = expand(
        "easy_strides", {"minutes": 35, "hr_high": 150, "reps": 4}
    )
    seconds, _km = structure_totals(structure)
    assert seconds == 35 * 60
    assert title == "イージー 35分＋流し 4本（〜150）"
