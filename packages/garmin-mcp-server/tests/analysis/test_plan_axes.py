"""Plan-check axes derived from the prescription structure (Issue #1404)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from garmin_mcp.analysis.plan_axes import AxisResult, evaluate_structure_axes
from garmin_mcp.analysis.purpose_outcome import evaluate as evaluate_outcome
from garmin_mcp.analysis.workout_alignment import Alignment, align_segments
from garmin_mcp.analysis.workout_structure import Structure, validate_structure

WU10: dict[str, Any] = {"step_type": "warmup", "duration_minutes": 10}
CD5: dict[str, Any] = {"step_type": "cooldown", "duration_minutes": 5}
STAGE_BANDS = [(136, 150), (136, 150), (151, 161), (162, 165), (166, 169)]


def _lap(
    split_index: int,
    step_index: int | None,
    intensity: str,
    distance_km: float,
    duration_s: float,
    avg_hr: float | None = 140.0,
) -> dict[str, Any]:
    return {
        "split_index": split_index,
        "distance_km": distance_km,
        "pace_s_per_km": duration_s / distance_km if distance_km else None,
        "avg_hr": avg_hr,
        "intensity_type": intensity,
        "duration_s": duration_s,
        "workout_step_index": step_index,
    }


def _laps(
    spec: list[tuple[int | None, str, float, float, float | None]],
) -> list[dict[str, Any]]:
    return [
        _lap(i, step, intensity, km, secs, hr)
        for i, (step, intensity, km, secs, hr) in enumerate(spec, start=1)
    ]


def _structure(raw: list[dict[str, Any]]) -> Structure:
    return validate_structure(raw, title="test")


def _trace(seconds: int, hr: Callable[[int], float]) -> list[dict[str, Any]]:
    return [{"timestamp_s": float(t), "heart_rate": hr(t)} for t in range(seconds)]


def _axes(
    structure: Structure,
    splits: list[dict[str, Any]],
    *,
    samples: list[dict[str, Any]] | None = None,
    purpose: str = "threshold",
    alignment: Alignment | None = None,
) -> dict[str, AxisResult]:
    samples = samples or []
    result = evaluate_structure_axes(
        structure,
        alignment if alignment is not None else align_segments(structure, splits),
        splits=splits,
        samples=samples,
        steady=[True] * len(samples),
        purpose=purpose,
    )
    ids = [axis.axis for axis in result]
    assert len(ids) == len(set(ids)), ids
    return {axis.axis: axis for axis in result}


# --- stages --------------------------------------------------------------------


def _stages_structure() -> Structure:
    return _structure(
        [
            {"step_type": "warmup", "distance_m": 1000},
            *(
                {"step_type": "run", "distance_m": 1000, "hr_low": lo, "hr_high": hi}
                for lo, hi in STAGE_BANDS
            ),
            {"step_type": "cooldown", "distance_m": 1000},
        ]
    )


def _stages_splits(stage_hr: list[float]) -> list[dict[str, Any]]:
    paces = [400.0, 380.0, 355.0, 335.0, 320.0]
    return _laps(
        [
            (0, "WARMUP", 1.0, 420.0, 128.0),
            *(
                (i + 1, "INTERVAL", 1.0, pace, hr)
                for i, (pace, hr) in enumerate(zip(paces, stage_hr, strict=True))
            ),
            (6, "COOLDOWN", 1.0, 400.0, 150.0),
        ]
    )


@pytest.mark.unit
def test_stages_build_up_on_plan() -> None:
    axes = _axes(
        _stages_structure(),
        _stages_splits([142, 150, 157, 164, 168]),
        purpose="progression",
    )

    assert axes["stages"].status == "on_plan"
    assert axes["stages"].severity == 0
    assert "continuity" not in axes
    assert "hr_band" not in axes


@pytest.mark.unit
def test_stages_final_not_reached() -> None:
    axes = _axes(_stages_structure(), _stages_splits([142, 150, 157, 164, 160]))

    stages = axes["stages"]
    assert stages.status == "off_plan"
    assert stages.severity == 1
    assert "最終段 160 < 166" in stages.actual


@pytest.mark.unit
def test_stages_not_rising() -> None:
    # Stages 1 and 2 share 136-150: both in band, but HR falls 150 -> 147.
    axes = _axes(_stages_structure(), _stages_splits([150, 147, 157, 164, 168]))

    assert axes["stages"].status == "off_plan"
    assert axes["stages"].severity == 1


# --- cruise intervals -------------------------------------------------------------


def _cruise_structure() -> Structure:
    return _structure(
        [
            WU10,
            {
                "repeat_count": 4,
                "steps": [
                    {
                        "step_type": "run",
                        "duration_seconds": 300,
                        "hr_low": 162,
                        "hr_high": 169,
                    },
                    {"step_type": "recovery", "duration_seconds": 60},
                ],
            },
            CD5,
        ]
    )


def _cruise_run(reps: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spec: list[tuple[int | None, str, float, float, float | None]] = [
        (0, "WARMUP", 1.4, 600.0, 130.0)
    ]
    for _ in range(reps):
        spec.append((1, "INTERVAL", 1.0, 300.0, 162.0))
        spec.append((2, "RECOVERY", 0.15, 60.0, 145.0))
    spec.append((4, "COOLDOWN", 0.7, 300.0, 140.0))
    total = 600 + reps * 360 + 300

    def hr(t: int) -> float:
        if t < 600 or t >= 600 + reps * 360:
            return 130.0
        into = (t - 600) % 360
        if into >= 300:
            return 145.0
        return 150.0 + 12.0 * into / 90.0 if into < 90 else 165.0

    return _laps(spec), _trace(total, hr)


@pytest.mark.unit
def test_cruise_4x5_reps_and_band() -> None:
    splits, samples = _cruise_run(4)

    axes = _axes(_cruise_structure(), splits, samples=samples)

    assert axes["reps"].status == "on_plan"
    assert axes["reps"].actual.startswith("4/4")
    band = axes["hr_band"]
    assert band.status == "on_plan"
    assert "帯内 100%" in band.actual
    assert [s["in_band_pct"] for s in band.segments] == [100.0] * 4


@pytest.mark.unit
def test_cruise_three_of_four_reps() -> None:
    splits, samples = _cruise_run(3)

    axes = _axes(_cruise_structure(), splits, samples=samples)

    assert axes["reps"].status == "short"
    assert axes["reps"].severity == 1
    assert axes["reps"].actual.startswith("3/4")


# --- VO2 max reps -----------------------------------------------------------------


@pytest.mark.unit
def test_vo2_2min_no_hr_band() -> None:
    structure = _structure(
        [
            WU10,
            {
                "repeat_count": 9,
                "steps": [
                    {
                        "step_type": "run",
                        "duration_seconds": 120,
                        "hr_low": 170,
                        "hr_high": 180,
                    },
                    {"step_type": "recovery", "duration_seconds": 120},
                ],
            },
            CD5,
        ]
    )
    spec: list[tuple[int | None, str, float, float, float | None]] = [
        (0, "WARMUP", 1.4, 600.0, 130.0)
    ]
    for rep in range(9):
        spec.append((1, "INTERVAL", 0.48 + 0.002 * (rep % 3), 120.0, 172.0))
        spec.append((2, "RECOVERY", 0.3, 120.0, 150.0))
    spec.append((4, "COOLDOWN", 0.7, 300.0, 140.0))
    splits = _laps(spec)

    axes = _axes(structure, splits, samples=_trace(3060, lambda _t: 185.0))

    assert "hr_band" not in axes
    assert list(axes) == ["reps"]
    assert axes["reps"].status == "on_plan"
    assert "ペース差" in axes["reps"].actual

    # Inconsistent reps: the second rep ~10% slower than the rest.
    splits[3]["distance_km"] = 0.44
    uneven = _axes(structure, splits)
    assert uneven["reps"].status == "off_plan"
    assert uneven["reps"].severity == 1


# --- long run with a marathon-pace block ----------------------------------------


def _long_mp(mp_pace: float) -> dict[str, AxisResult]:
    structure = _structure(
        [
            {"step_type": "run", "duration_minutes": 60, "hr_high": 150},
            {
                "step_type": "run",
                "duration_minutes": 30,
                "hr_high": 158,
                "pace_low_s_per_km": 380,
                "pace_high_s_per_km": 385,
            },
            {"step_type": "run", "duration_minutes": 10, "hr_high": 150},
        ]
    )
    splits = _laps(
        [
            (0, "ACTIVE", 3600 / 420, 3600.0, 140.0),
            (1, "ACTIVE", 1800 / mp_pace, 1800.0, 155.0),
            (2, "ACTIVE", 600 / 430, 600.0, 140.0),
        ]
    )
    samples = _trace(6000, lambda t: 155.0 if 3600 <= t < 5400 else 140.0)
    return _axes(structure, splits, samples=samples, purpose="long_goal_pace")


@pytest.mark.unit
def test_long_mp_ceiling_per_segment() -> None:
    on_pace = _long_mp(382.0)

    assert on_pace["hr_ceiling"].status == "on_plan"
    assert on_pace["hr_ceiling"].target == "区間別 150/158 bpm 以下"
    assert [s["on_plan"] for s in on_pace["hr_ceiling"].segments] == [True] * 3
    assert on_pace["pace_band"].status == "on_plan"
    assert "continuity" not in on_pace

    slow = _long_mp(395.0)

    assert slow["hr_ceiling"].status == "on_plan"
    assert slow["pace_band"].status == "off_plan"
    assert slow["pace_band"].severity == 1


# --- optional steps ---------------------------------------------------------------


@pytest.mark.unit
def test_optional_segment_not_taken_is_not_deviation() -> None:
    structure = _structure(
        [
            {"step_type": "run", "duration_minutes": 60, "hr_high": 150},
            {
                "step_type": "run",
                "duration_minutes": 10,
                "hr_high": 165,
                "pace_low_s_per_km": 360,
                "pace_high_s_per_km": 370,
                "optional": True,
            },
        ]
    )
    splits = _laps([(0, "ACTIVE", 1.0, 400.0, 140.0)] * 9)

    axes = _axes(structure, splits, purpose="long_easy")

    assert "pace_band" not in axes
    assert axes["hr_ceiling"].target == "150 bpm 以下"
    assert len(axes["hr_ceiling"].segments) == 1
    assert all(axis.severity == 0 for axis in axes.values())


# --- continuity -------------------------------------------------------------------


@pytest.mark.unit
def test_single_step_continuity_ignores_warmup() -> None:
    structure = _structure(
        [WU10, {"step_type": "run", "duration_minutes": 30, "hr_high": 150}]
    )
    splits = _laps(
        [
            (0, "WARMUP", 1.0, 450.0, 125.0),
            (0, "WARMUP", 1 / 3, 150.0, 128.0),
            (1, "ACTIVE", 1.0, 370.0, 140.0),
            (1, "ACTIVE", 1.0, 370.0, 142.0),
            (1, "ACTIVE", 1.0, 370.0, 144.0),
            (1, "ACTIVE", 1.0, 480.0, 138.0),
            (1, "ACTIVE", 1.0, 480.0, 136.0),
        ]
    )
    # The whole run's opening third holds the 7:30 warmup, so read over every
    # lap the 8:00 finish still looks "held".
    assert evaluate_outcome("easy", splits) is not None
    assert evaluate_outcome("easy", splits).met  # type: ignore[union-attr]

    axes = _axes(structure, splits, purpose="easy")

    continuity = axes["continuity"]
    assert continuity.status == "off_plan"
    assert continuity.severity == 1
    assert continuity.actual == "3 km から崩れ"


# --- alignment failure ------------------------------------------------------------


@pytest.mark.unit
def test_alignment_none_is_insufficient() -> None:
    none = Alignment(
        method="none",
        segments=(),
        missing=(),
        skipped_optional=(),
        reason="the laps carry no workout_step_index",
    )
    splits, samples = _cruise_run(4)

    cruise = _axes(_cruise_structure(), splits, samples=samples, alignment=none)
    stages = _axes(
        _stages_structure(), _stages_splits([142, 150, 157, 164, 168]), alignment=none
    )

    assert {"hr_band", "reps"} <= set(cruise)
    assert "stages" in stages
    for axis in [*cruise.values(), *stages.values()]:
        assert axis.status == "insufficient"
        assert axis.severity == 0


@pytest.mark.unit
def test_distance_band_step_listed_when_misaligned() -> None:
    """A legacy 8.5 km band body with no pace stays on the card, not judged."""
    structure = _structure(
        [
            WU10,
            {"step_type": "run", "distance_m": 8500, "hr_low": 136, "hr_high": 169},
            CD5,
        ]
    )
    none = Alignment(
        method="none",
        segments=(),
        missing=(),
        skipped_optional=(),
        reason="lap 4 carries step index 3",
    )

    axes = _axes(
        structure,
        _stages_splits([142, 150, 157, 164, 168]),
        alignment=none,
        purpose="progression",
    )

    assert axes["hr_band"].status == "insufficient"
    assert axes["hr_band"].target == "136-169 bpm"


# --- strides ----------------------------------------------------------------------


@pytest.mark.unit
def test_easy_strides_axis_id_kept() -> None:
    structure = _structure(
        [
            {"step_type": "run", "duration_seconds": 1700, "hr_high": 150},
            {
                "repeat_count": 4,
                "steps": [
                    {"step_type": "run", "duration_seconds": 20},
                    {"step_type": "recovery", "duration_seconds": 60},
                ],
            },
            {"step_type": "cooldown", "duration_minutes": 5, "hr_high": 150},
        ]
    )
    spec: list[tuple[int | None, str, float, float, float | None]] = [
        (0, "ACTIVE", 4.2, 1700.0, 143.0)
    ]
    for _ in range(4):
        spec.append((1, "INTERVAL", 0.1, 20.0, 150.0))
        spec.append((2, "RECOVERY", 0.15, 60.0, 148.0))
    spec.append((4, "COOLDOWN", 0.7, 300.0, 145.0))

    axes = _axes(structure, _laps(spec), purpose="easy")

    assert "strides" in axes
    assert "reps" not in axes
    assert axes["strides"].status == "on_plan"
    assert axes["strides"].actual == "4本"
    assert axes["hr_ceiling"].status == "on_plan"
