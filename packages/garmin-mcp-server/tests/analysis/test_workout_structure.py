"""Tests for the prescription step structure module (Issue #1400)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.workout_structure import (
    fit_step_indices,
    registrable_steps,
    registration_fingerprint,
    structure_totals,
    synthesize_structure,
    validate_structure,
)
from garmin_mcp.tools.workout_scheduling import build_steps_from_prescription

WU10: dict[str, Any] = {"step_type": "warmup", "duration_minutes": 10}
CD5: dict[str, Any] = {"step_type": "cooldown", "duration_minutes": 5}

# Golden outputs of the pre-refactor ``build_steps_from_prescription``.
_LEGACY_CASES: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
    (
        "easy_35min",
        {"session_type": "easy", "target_minutes": 35, "hr_high": 150},
        [{"step_type": "run", "duration_minutes": 35, "hr_high": 150}],
    ),
    (
        "easy_35min_strides",
        {
            "session_type": "easy",
            "target_minutes": 35,
            "hr_high": 150,
            "strides": {"reps": 4, "run_seconds": 20, "recovery_seconds": 90},
        },
        [
            {"step_type": "run", "duration_seconds": 1360, "hr_high": 150},
            {
                "repeat_count": 4,
                "steps": [
                    {"step_type": "run", "duration_seconds": 20},
                    {"step_type": "recovery", "duration_seconds": 90},
                ],
            },
            {"step_type": "cooldown", "duration_minutes": 5, "hr_high": 150},
        ],
    ),
    (
        "threshold_20min",
        {
            "session_type": "threshold",
            "target_minutes": 20,
            "hr_low": 162,
            "hr_high": 169,
        },
        [
            {"step_type": "warmup", "duration_minutes": 10},
            {
                "step_type": "run",
                "duration_minutes": 20,
                "hr_low": 162,
                "hr_high": 169,
            },
            {"step_type": "cooldown", "duration_minutes": 5},
        ],
    ),
    (
        "long_16km",
        {"session_type": "long", "target_km": 16.0, "hr_high": 150},
        [{"step_type": "run", "distance_m": 16000, "hr_high": 150}],
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "golden"),
    [(row, golden) for _, row, golden in _LEGACY_CASES],
    ids=[name for name, _, _ in _LEGACY_CASES],
)
def test_synthesize_matches_registration_legacy(
    row: dict[str, Any], golden: list[dict[str, Any]]
) -> None:
    """Legacy rows synthesize to exactly the workout registration always built."""
    structure = synthesize_structure(row)

    assert structure == golden
    assert build_steps_from_prescription(row) == golden


@pytest.mark.unit
def test_synthesize_rest_returns_none() -> None:
    assert synthesize_structure({"session_type": "rest"}) is None


@pytest.mark.unit
def test_synthesize_prefers_structure_column() -> None:
    """A stored structure wins over the legacy columns and is returned verbatim."""
    stored = [
        WU10,
        {"step_type": "run", "duration_minutes": 20, "hr_low": 162, "hr_high": 169},
        CD5,
    ]
    row = {
        "session_type": "threshold",
        "title": "Threshold 20",
        "target_minutes": 30,
        "hr_low": 162,
        "hr_high": 169,
        "structure": stored,
    }

    assert synthesize_structure(row) == stored


@pytest.mark.unit
def test_registrable_drops_optional_and_pace() -> None:
    structure = [
        {"step_type": "run", "distance_m": 15000, "hr_high": 150},
        {
            "step_type": "run",
            "distance_m": 3000,
            "optional": True,
            "pace_low_s_per_km": 365,
            "pace_high_s_per_km": 370,
        },
    ]

    steps = registrable_steps(validate_structure(structure, title="long + finish"))

    assert steps == [{"step_type": "run", "distance_m": 15000, "hr_high": 150}]
    assert all("pace_low_s_per_km" not in s for s in steps)
    assert all("pace_high_s_per_km" not in s for s in steps)


@pytest.mark.unit
def test_fit_indices_repeat_marker_after_children() -> None:
    structure = [
        WU10,
        {
            "repeat_count": 4,
            "steps": [
                {"step_type": "run", "duration_minutes": 5},
                {"step_type": "recovery", "duration_minutes": 3},
            ],
        },
        CD5,
    ]

    flat = fit_step_indices(structure)  # type: ignore[arg-type]

    assert [(f.step["step_type"], f.fit_index) for f in flat] == [
        ("warmup", 0),
        ("run", 1),
        ("recovery", 2),
        ("cooldown", 4),
    ]
    assert flat[1].path == (1, 0)
    assert flat[1].group_path == (1,)
    assert flat[1].repeat_count == 4
    assert flat[0].group_path is None
    assert flat[0].repeat_count == 1


@pytest.mark.unit
def test_fit_indices_nested_superset() -> None:
    """Superset as run on activity 20652528219: markers follow their children."""
    structure = [
        WU10,
        {
            "repeat_count": 2,
            "steps": [
                {
                    "repeat_count": 3,
                    "steps": [
                        {"step_type": "run", "duration_seconds": 15},
                        {"step_type": "rest", "duration_seconds": 45},
                    ],
                },
                {"step_type": "recovery", "duration_seconds": 300},
            ],
        },
        CD5,
    ]

    flat = fit_step_indices(validate_structure(structure, title="superset"))

    assert [(f.step["step_type"], f.fit_index) for f in flat] == [
        ("warmup", 0),
        ("run", 1),
        ("rest", 2),
        ("recovery", 4),
        ("cooldown", 6),
    ]
    run = flat[1]
    assert run.path == (1, 0, 0)
    assert run.group_path == (1, 0)
    assert run.repeat_count == 6
    assert flat[3].group_path == (1,)
    assert flat[3].repeat_count == 2


_RUN = {"step_type": "run", "duration_minutes": 20}


@pytest.mark.unit
@pytest.mark.parametrize(
    "structure",
    [
        pytest.param([{**_RUN, "hr_low": 170, "hr_high": 160}], id="hr_low_above_high"),
        pytest.param([{**_RUN, "hr_high": "Z4"}], id="hr_zone_label"),
        pytest.param([{"repeat_count": 0, "steps": [_RUN]}], id="repeat_count_zero"),
        pytest.param([{**_RUN, "distance_m": 5000}], id="two_duration_keys"),
        pytest.param([{"step_type": "run", "hr_high": 150}], id="no_duration"),
        pytest.param(
            [{"repeat_count": 3, "steps": [{**_RUN, "optional": True}]}],
            id="optional_inside_group",
        ),
    ],
)
def test_validate_structure_rejects(structure: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="Bad plan"):
        validate_structure(structure, title="Bad plan")


@pytest.mark.unit
def test_validate_structure_accepts_build_up() -> None:
    """The 2026-09-09 build-up: one band per kilometre between 1 km bookends."""
    bands = [(136, 150), (136, 150), (151, 161), (162, 165), (166, 169)]
    structure = [
        {"step_type": "warmup", "distance_m": 1000},
        *(
            {"step_type": "run", "distance_m": 1000, "hr_low": lo, "hr_high": hi}
            for lo, hi in bands
        ),
        {"step_type": "cooldown", "distance_m": 1000},
    ]
    snapshot = [dict(s) for s in structure]

    result = validate_structure(structure, title="Build-up 5km")

    assert result is structure
    assert result == snapshot


@pytest.mark.unit
def test_structure_totals_timed() -> None:
    structure = [
        WU10,
        {
            "repeat_count": 4,
            "steps": [
                {"step_type": "run", "duration_minutes": 5},
                {"step_type": "recovery", "duration_minutes": 3},
            ],
        },
        CD5,
    ]

    assert structure_totals(structure) == (2820.0, None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_structure_totals_mixed_is_none() -> None:
    structure = [WU10, {"step_type": "run", "distance_m": 5000}]

    assert structure_totals(structure) == (None, None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_registration_fingerprint_ignores_judge_only_fields() -> None:
    """Only what the watch receives counts: title + registrable steps (#1447)."""
    long_run: dict[str, Any] = {
        "session_type": "long",
        "title": "ロング28km",
        "target_minutes": None,
        "target_km": 28.0,
        "hr_low": None,
        "hr_high": 150,
        "rationale": "最終ロング",
    }
    judge_only_edit = {
        **long_run,
        "rationale": "補給は45分ごと",
        "allowances": {"walk": True},
        "purpose": "long_easy",
        "pace_low_s_per_km": 420,
    }

    fingerprint = registration_fingerprint(long_run)
    assert fingerprint is not None
    assert registration_fingerprint(judge_only_edit) == fingerprint
    assert registration_fingerprint({**long_run, "hr_high": 145}) != fingerprint
    assert registration_fingerprint({**long_run, "title": "ロング26km"}) != fingerprint
    assert registration_fingerprint({"session_type": "rest", "title": "休養"}) is None
