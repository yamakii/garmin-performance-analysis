"""Strides are strides, and the jog around them is judged as an easy run (#1297).

An easy run with strides is a jog read in kilometres plus one block of short,
fast efforts. The block is one ``strides`` scene; it never turns the run into a
rep session, never counts as a ceiling touch and never makes a recurrence.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.run_moments import (
    build_flow,
    build_steps,
    detect_moments,
    detect_recurrence,
)

from .splits import _split

HR_CEILING = 150


def _lap(
    index: int,
    distance_km: float,
    duration_s: float,
    role: str,
    avg_hr: float,
    max_hr: float,
    *,
    cadence: float = 178.0,
    step_index: int | None = None,
) -> dict[str, Any]:
    """One split row with a role, timing, cadence and workout step index."""
    row = _split(
        index,
        duration_s / distance_km,
        avg_hr,
        max_hr,
        cadence=cadence,
        distance_km=distance_km,
    )
    row["duration_s"] = duration_s
    row["role_phase"] = role
    row["workout_step_index"] = step_index
    return row


def _strides_session(*, final_jog: bool = False) -> list[dict[str, Any]]:
    """3 x 1 km jog, 4 x (20 s stride ~3:30/km / 90 s jog), 5 min cooldown.

    ``final_jog`` adds a 1 km ``run`` lap after the strides -- the jog either
    side of the block that would otherwise pass for two reps.
    """
    laps: list[dict[str, Any]] = [
        _lap(i, 1.0, 420, "run", 144, 148, step_index=0) for i in range(1, 4)
    ]
    index = 4
    for rep in range(4):
        laps.append(
            _lap(
                index,
                0.095,
                20,
                "stride",
                150 + rep,
                164,
                cadence=210 + rep,
                step_index=1,
            )
        )
        laps.append(_lap(index + 1, 0.19, 90, "recovery", 155 - rep, 160, step_index=2))
        index += 2
    if final_jog:
        laps.append(_lap(index, 1.0, 420, "run", 144, 148, step_index=3))
        index += 1
    laps.append(_lap(index, 0.65, 300, "cooldown", 138, 145, step_index=4))
    return laps


@pytest.mark.unit
def test_strides_scene_collapses_reps() -> None:
    """Four strides and their jogs are one scene, not four reps and four rests."""
    moments = detect_moments(_strides_session(), hr_ceiling=HR_CEILING)

    strides = [m for m in moments if m["kind"] == "strides"]
    assert len(strides) == 1
    scene = strides[0]
    assert scene["unit"] == "step"
    assert scene["label_ja"] == "流し（4本）"
    facts = scene["facts"]
    assert facts["reps"] == 4
    assert facts["fastest_pace_s_per_km"] == pytest.approx(210.5, abs=0.1)
    assert facts["median_pace_s_per_km"] == pytest.approx(210.5, abs=0.1)
    assert facts["median_cadence_spm"] == pytest.approx(211.5)
    assert facts["peak_hr"] == 164
    assert facts["hr_at_next_start"] == [155, 154, 153, 152]
    assert not {"rep", "rest"} & {m["kind"] for m in moments}
    assert scene["km_from"] == pytest.approx(3.0)
    assert scene["km_to"] == pytest.approx(3.0 + 4 * (0.095 + 0.19))


@pytest.mark.unit
def test_ceiling_touch_ignores_stride_steps() -> None:
    """A stride peaking at 164 and a jog averaging 155 are not a ceiling touch.

    The jog laps average 144 against a 150 ceiling; only they are judged.
    """
    moments = detect_moments(_strides_session(), hr_ceiling=HR_CEILING)

    assert "ceiling_touch" not in {m["kind"] for m in moments}


@pytest.mark.unit
def test_step_break_on_workout_step_index() -> None:
    """Before #1296 the first stride carried ``run`` like the jog before it.

    Only the workout step index tells the two apart.
    """
    splits = [
        _lap(1, 1.0, 420, "run", 144, 148, step_index=0),
        _lap(2, 0.095, 20, "run", 150, 164, step_index=1),
    ]

    steps = build_steps(splits)

    assert len(steps) == 2
    assert [(s["split_from"], s["split_to"]) for s in steps] == [(1, 1), (2, 2)]


@pytest.mark.unit
def test_flow_axis_stays_distance_with_strides() -> None:
    """A jog with strides is read in kilometres, with or without a closing jog."""
    assert build_flow(_strides_session())["axis"] == "distance"
    assert build_flow(_strides_session(final_jog=True))["axis"] == "distance"
    moments = detect_moments(_strides_session(final_jog=True), hr_ceiling=HR_CEILING)
    assert not {"rep", "rest", "work_set"} & {m["kind"] for m in moments}


@pytest.mark.unit
def test_recurrence_skips_strides_kind() -> None:
    """Strides are prescribed: doing them again is the plan, not a habit."""
    today = detect_moments(_strides_session(), hr_ceiling=HR_CEILING)
    previous = [
        {
            "activity_date": f"2026-09-{day:02d}",
            "moments": detect_moments(_strides_session(), hr_ceiling=HR_CEILING),
        }
        for day in (18, 15, 11)
    ]

    recurrence = detect_recurrence(today, previous)

    assert "strides" in {m["kind"] for m in today}
    assert "strides" not in {entry["kind"] for entry in recurrence}
