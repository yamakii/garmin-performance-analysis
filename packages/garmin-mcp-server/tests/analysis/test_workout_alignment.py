"""Tests for aligning prescription steps to laps (Issue #1402)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.workout_alignment import align_segments
from garmin_mcp.analysis.workout_structure import Structure, validate_structure

WU10: dict[str, Any] = {"step_type": "warmup", "duration_minutes": 10}
CD5: dict[str, Any] = {"step_type": "cooldown", "duration_minutes": 5}


def _lap(
    split_index: int,
    step_index: int | None,
    intensity: str,
    distance_km: float,
    duration_s: float,
    avg_hr: float | None = 140.0,
) -> dict[str, Any]:
    """One lap row in the shape the run report reads splits."""
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
    spec: list[tuple[int | None, str, float, float, float]],
) -> list[dict[str, Any]]:
    return [
        _lap(i, step, intensity, km, secs, hr)
        for i, (step, intensity, km, secs, hr) in enumerate(spec, start=1)
    ]


def _structure(raw: list[dict[str, Any]]) -> Structure:
    return validate_structure(raw, title="test")


@pytest.mark.unit
def test_align_build_up_24294972923() -> None:
    """The 2026-09-09 build-up: 1 km bookends around five 1 km HR stages."""
    bands = [(136, 150), (136, 150), (151, 161), (162, 165), (166, 169)]
    structure = _structure(
        [
            {"step_type": "warmup", "distance_m": 1000},
            *(
                {"step_type": "run", "distance_m": 1000, "hr_low": lo, "hr_high": hi}
                for lo, hi in bands
            ),
            {"step_type": "cooldown", "distance_m": 1000},
        ]
    )
    splits = _laps(
        [
            (0, "WARMUP", 1.0, 420.0, 128.0),
            (1, "INTERVAL", 1.0, 400.0, 142.0),
            (2, "INTERVAL", 1.0, 380.0, 150.0),
            (3, "INTERVAL", 1.0, 355.0, 157.0),
            (4, "INTERVAL", 1.0, 335.0, 164.0),
            (5, "INTERVAL", 1.0, 320.0, 168.0),
            (6, "COOLDOWN", 1.0, 400.0, 155.0),
            (6, "COOLDOWN", 1.0, 410.0, 148.0),
            (6, "COOLDOWN", 0.5, 215.0, 144.0),
            (None, "ACTIVE", 0.03, 13.0, 143.0),
        ]
    )

    alignment = align_segments(structure, splits)

    assert alignment.method == "step_index"
    assert alignment.reason is None
    assert [s.segment_id for s in alignment.segments] == [str(i) for i in range(7)]
    assert alignment.missing == ()
    stages = [s for s in alignment.segments if s.step["step_type"] == "run"]
    assert [s.avg_hr for s in stages] == [142, 150, 157, 164, 168]
    cooldown = alignment.segments[-1]
    assert cooldown.split_indices == (7, 8, 9, 10)
    assert cooldown.duration_s == 1038.0
    assert cooldown.distance_km == 2.53
    assert alignment.segments[1].start_s == 420.0
    assert alignment.segments[1].pace_s_per_km == 400.0


@pytest.mark.unit
def test_align_autolap_splits_one_step() -> None:
    structure = _structure(
        [
            {"step_type": "warmup", "distance_m": 1000},
            {"step_type": "run", "distance_m": 5000},
            {"step_type": "cooldown", "distance_m": 1000},
        ]
    )
    splits = _laps(
        [
            (0, "WARMUP", 1.0, 420.0, 130.0),
            *[(1, "ACTIVE", 1.0, 330.0, 160.0)] * 5,
            (2, "COOLDOWN", 1.0, 420.0, 145.0),
        ]
    )

    alignment = align_segments(structure, splits)

    assert alignment.method == "step_index"
    run = alignment.segments[1]
    assert run.segment_id == "1"
    assert run.split_indices == (2, 3, 4, 5, 6)
    assert run.distance_km == 5.0
    assert run.avg_hr == 160.0
    assert len(alignment.segments) == 3


@pytest.mark.unit
def test_align_skipped_last_recovery() -> None:
    """9 x (2 min, 60 s) from 20615445009, stopped before the last recovery."""
    structure = _structure(
        [
            WU10,
            {
                "repeat_count": 9,
                "steps": [
                    {"step_type": "run", "duration_seconds": 120},
                    {"step_type": "recovery", "duration_seconds": 60},
                ],
            },
            CD5,
        ]
    )
    spec: list[tuple[int | None, str, float, float, float]] = [
        (0, "WARMUP", 1.6, 600.0, 130.0)
    ]
    for rep in range(9):
        spec.append((1, "INTERVAL", 0.5, 120.0, 165.0))
        if rep < 8:
            spec.append((2, "RECOVERY", 0.15, 60.0, 150.0))
    spec.append((4, "COOLDOWN", 0.8, 300.0, 140.0))

    alignment = align_segments(structure, _laps(spec))

    assert alignment.method == "step_index"
    work = [s for s in alignment.segments if s.step["step_type"] == "run"]
    assert len(work) == 9
    assert [s.segment_id for s in work] == [f"1#{i}" for i in range(1, 10)]
    assert [s.iteration for s in work] == list(range(1, 10))
    assert alignment.missing == ("2#9",)
    assert alignment.segments[-1].segment_id == "4"


@pytest.mark.unit
def test_align_nested_superset_20652528219() -> None:
    structure = _structure(
        [
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
    )
    spec: list[tuple[int | None, str, float, float, float]] = [
        (0, "WARMUP", 1.6, 600.0, 130.0)
    ]
    for _ in range(2):
        for _ in range(3):
            spec.append((1, "INTERVAL", 0.08, 15.0, 150.0))
            spec.append((2, "REST", 0.0, 45.0, 135.0))
        spec.append((4, "RECOVERY", 0.8, 300.0, 140.0))
    spec.append((6, "COOLDOWN", 0.8, 300.0, 138.0))

    alignment = align_segments(structure, _laps(spec))

    assert alignment.method == "step_index"
    assert alignment.missing == ()
    assert [s.segment_id for s in alignment.segments] == [
        "0",
        "1#1",
        "2#1",
        "1#2",
        "2#2",
        "1#3",
        "2#3",
        "4#1",
        "1#4",
        "2#4",
        "1#5",
        "2#5",
        "1#6",
        "2#6",
        "4#2",
        "6",
    ]
    work = [s for s in alignment.segments if s.step["step_type"] == "run"]
    assert len(work) == 6
    rest = [s for s in alignment.segments if s.step["step_type"] == "rest"]
    assert rest[0].pace_s_per_km is None


@pytest.mark.unit
def test_align_fingerprint_mismatch() -> None:
    """A plain run on one watch step cannot stand in for WU / run / CD."""
    structure = _structure([WU10, {"step_type": "run", "duration_minutes": 20}, CD5])
    splits = _laps([(0, "ACTIVE", 1.0, 360.0, 145.0)] * 3)

    alignment = align_segments(structure, splits)

    assert alignment.method == "none"
    assert alignment.reason
    assert alignment.segments == ()


@pytest.mark.unit
def test_align_intensity_mismatch_is_none() -> None:
    structure = _structure([WU10, {"step_type": "run", "duration_minutes": 20}, CD5])
    splits = _laps(
        [
            (0, "WARMUP", 1.5, 600.0, 130.0),
            (1, "RECOVERY", 3.0, 1200.0, 160.0),
            (2, "COOLDOWN", 0.8, 300.0, 140.0),
        ]
    )

    alignment = align_segments(structure, splits)

    assert alignment.method == "none"
    assert "RECOVERY" in (alignment.reason or "")


@pytest.mark.unit
def test_align_out_of_order_is_none() -> None:
    structure = _structure([WU10, {"step_type": "run", "duration_minutes": 20}, CD5])
    splits = _laps(
        [
            (0, "WARMUP", 1.5, 600.0, 130.0),
            (2, "COOLDOWN", 0.8, 300.0, 140.0),
            (1, "ACTIVE", 3.0, 1200.0, 160.0),
        ]
    )

    alignment = align_segments(structure, splits)

    assert alignment.method == "none"
    assert "step index 1" in (alignment.reason or "")


@pytest.mark.unit
def test_align_no_step_index() -> None:
    structure = _structure([{"step_type": "run", "duration_minutes": 30}])
    splits = [
        {"split_index": i, "distance_km": 1.0, "duration_s": 360.0, "avg_hr": 145}
        for i in range(1, 6)
    ]

    alignment = align_segments(structure, splits)

    assert alignment.method == "none"
    assert "workout_step_index" in (alignment.reason or "")


@pytest.mark.unit
def test_align_optional_step_not_taken() -> None:
    structure = _structure(
        [
            {"step_type": "run", "distance_m": 15000, "hr_high": 150},
            {"step_type": "run", "distance_m": 3000, "optional": True},
        ]
    )
    splits = _laps([(0, "ACTIVE", 5.0, 1900.0, 145.0)] * 3)

    alignment = align_segments(structure, splits)

    assert alignment.method == "step_index"
    assert [s.segment_id for s in alignment.segments] == ["0"]
    assert alignment.skipped_optional == ("1",)
    assert alignment.missing == ()


@pytest.mark.unit
def test_align_optional_step_taken() -> None:
    """The fast finish runs after the watch workout ended: an unindexed tail."""
    structure = _structure(
        [
            {"step_type": "run", "distance_m": 15000, "hr_high": 150},
            {"step_type": "run", "distance_m": 3000, "optional": True},
        ]
    )
    splits = _laps(
        [
            *[(0, "ACTIVE", 5.0, 1900.0, 145.0)] * 3,
            *[(None, "ACTIVE", 1.0, 330.0, 160.0)] * 3,
        ]
    )

    alignment = align_segments(structure, splits)

    assert alignment.method == "step_index"
    assert [s.segment_id for s in alignment.segments] == ["0", "1"]
    finish = alignment.segments[1]
    assert finish.split_indices == (4, 5, 6)
    assert finish.step.get("optional") is True
    assert alignment.skipped_optional == ()
