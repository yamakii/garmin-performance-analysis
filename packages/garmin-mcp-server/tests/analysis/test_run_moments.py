"""Tests for deterministic run scene detection (#1249).

The scenes are what the split section is allowed to narrate, so the rules are
pinned against realistic split shapes: a short tempo-ish run that touches the HR
ceiling and corrects (the 9/18 run), a 25 km long run with scattered walk breaks
and a strong finish, and a synthetic run that fires every rule at once to
exercise the priority cap.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from garmin_mcp.analysis import run_moments
from garmin_mcp.analysis.run_moments import detect_moments, detect_recurrence


def _split(
    split_index: int,
    pace: float,
    avg_hr: float,
    max_hr: float,
    *,
    cadence: float = 178.0,
    elevation_gain_m: float = 2.0,
    distance_km: float = 1.0,
) -> dict[str, Any]:
    """One split row in the shape the reader hands to the detector."""
    return {
        "split_index": split_index,
        "distance_km": distance_km,
        "pace_s_per_km": pace,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "cadence": cadence,
        "elevation_gain_m": elevation_gain_m,
    }


def _ceiling_touch_run() -> list[dict[str, Any]]:
    """The 9/18 run: HR climbs onto the 150 ceiling at km 3, eased off at km 4."""
    paces = [413, 407, 419, 432, 413]
    avg_hrs = [129, 145, 147, 148, 148]
    max_hrs = [140, 149, 151, 156, 155]
    return [
        _split(i, pace, avg_hr, max_hr)
        for i, (pace, avg_hr, max_hr) in enumerate(
            zip(paces, avg_hrs, max_hrs, strict=True), start=1
        )
    ]


def _long_run_with_walk_breaks() -> list[dict[str, Any]]:
    """25 km long run: walk breaks at km 14 / 20 / 22, median pace 510 s/km."""
    paces = [
        515,
        512,
        510,
        508,
        511,
        509,
        512,
        510,
        507,
        513,
        510,
        509,
        511,
        530,  # km 14 walk break
        512,
        508,
        510,
        514,
        509,
        563,  # km 20 walk break
        515,
        538,  # km 22 walk break
        486,
        473,
        461,  # strong finish
    ]
    avg_hrs = [
        138,
        140,
        141,
        142,
        142,
        143,
        143,
        144,
        144,
        145,
        145,
        145,
        146,
        136,  # HR falls on the walk break
        142,
        143,
        144,
        144,
        145,
        138,
        144,
        137,
        147,
        148,
        148,
    ]
    cadences = [178.0] * 25
    cadences[13] = 165.0
    cadences[19] = 159.0
    cadences[21] = 166.0
    return [
        _split(
            i,
            pace,
            avg_hr,
            min(149.0, avg_hr + 6),
            cadence=cadence,
            elevation_gain_m=3.0,
        )
        for i, (pace, avg_hr, cadence) in enumerate(
            zip(paces, avg_hrs, cadences, strict=True), start=1
        )
    ]


def _every_kind_run() -> list[dict[str, Any]]:
    """12 splits deliberately firing seven scenes (median pace 427.5 s/km).

    km 1 start, km 3 surge, km 4 climb, km 5 ceiling touch, km 6 self
    correction, km 8 walk break, km 10-12 fade.
    """
    rows = [
        # (pace, avg_hr, max_hr, cadence, elevation_gain_m)
        (420, 130, 140, 176, 2),
        (421, 138, 145, 176, 3),
        (405, 142, 147, 178, 2),
        (425, 143, 147, 176, 18),
        (430, 146, 151, 175, 20),
        (445, 146, 149, 174, 5),
        (420, 143, 147, 176, 2),
        (550, 138, 145, 160, 2),
        (425, 144, 148, 176, 3),
        (445, 146, 148, 175, 3),
        (450, 147, 149, 175, 3),
        (455, 147, 149, 174, 3),
    ]
    return [
        _split(i, pace, avg_hr, max_hr, cadence=cadence, elevation_gain_m=gain)
        for i, (pace, avg_hr, max_hr, cadence, gain) in enumerate(rows, start=1)
    ]


def _kinds_by_km(moments: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """``{kind: (km_from, km_to)}`` for readable assertions."""
    return {m["kind"]: (m["km_from"], m["km_to"]) for m in moments}


# --- detect_moments ---------------------------------------------------------


@pytest.mark.unit
def test_ceiling_touch_and_self_correction_detected() -> None:
    """Crossing the 150 ceiling at km 3 and giving back 13 s/km at km 4.

    km 3 is the crossing (max 151 after 149), km 4 is the correction: 13 s/km
    slower than km 3 with km 5's average HR no longer climbing (148 -> 148).
    """
    moments = detect_moments(_ceiling_touch_run(), hr_ceiling=150)

    kinds = _kinds_by_km(moments)
    assert kinds["ceiling_touch"] == (3, 3)
    assert kinds["self_correction"] == (4, 4)
    touch = next(m for m in moments if m["kind"] == "ceiling_touch")
    assert touch["facts"]["max_hr"] == 151
    assert touch["facts"]["hr_ceiling"] == 150
    correction = next(m for m in moments if m["kind"] == "self_correction")
    assert correction["facts"]["pace_delta_s_per_km"] == 13


@pytest.mark.unit
def test_uneventful_run_yields_single_steady_moment() -> None:
    """A run where nothing turns is one ``steady`` scene, not a km readout."""
    splits = [
        _split(1, 500, 138, 146),
        _split(2, 502, 140, 147),
        _split(3, 499, 141, 148),
        _split(4, 501, 142, 148),
        _split(5, 500, 141, 147),
    ]

    moments = detect_moments(splits, hr_ceiling=150)

    assert len(moments) == 1
    assert moments[0]["kind"] == "steady"
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (1, 5)
    assert moments[0]["facts"]["hr_range"] == [138, 142]


@pytest.mark.unit
def test_fragment_splits_are_ignored() -> None:
    """A 14 m manual-lap fragment at 6:05/km must not invent a scene.

    Unfiltered it is both the fastest "split" of the run and its finish, so it
    would fake a surge / strong finish; at 0.014 km it is below MIN_SPLIT_KM.
    """
    baseline = detect_moments(_ceiling_touch_run(), hr_ceiling=150)

    with_fragment = detect_moments(
        [*_ceiling_touch_run(), _split(6, 365, 148, 152, distance_km=0.014)],
        hr_ceiling=150,
    )

    assert with_fragment == baseline


@pytest.mark.unit
def test_walk_breaks_grouped_with_km_list() -> None:
    """Three scattered walk breaks are one scene carrying every kilometre."""
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    walk = next(m for m in moments if m["kind"] == "walk_break")
    assert walk["facts"]["km_list"] == [14, 20, 22]
    assert (walk["km_from"], walk["km_to"]) == (14, 22)
    assert walk["facts"]["cadence"] == 159
    assert sum(1 for m in moments if m["kind"] == "walk_break") == 1


@pytest.mark.unit
def test_strong_finish_detected_on_long_run() -> None:
    """The closing 3 km at 8:06 -> 7:41 under the ceiling is a strong finish."""
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    finish = next(m for m in moments if m["kind"] == "strong_finish")
    assert (finish["km_from"], finish["km_to"]) == (23, 25)
    assert finish["facts"]["median_pace_s_per_km"] == 510
    assert finish["facts"]["pace_delta_s_per_km"] == 37


@pytest.mark.unit
def test_no_ceiling_means_no_ceiling_scenes() -> None:
    """Without a prescribed ceiling there is nothing to touch or correct to."""
    splits = _ceiling_touch_run()
    splits[3]["max_hr"] = 160

    with_ceiling = detect_moments(splits, hr_ceiling=150)
    without_ceiling = detect_moments(splits, hr_ceiling=None)

    assert "ceiling_touch" in _kinds_by_km(with_ceiling)
    kinds = {m["kind"] for m in without_ceiling}
    assert "ceiling_touch" not in kinds
    assert "self_correction" not in kinds


@pytest.mark.unit
def test_moments_capped_and_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seven scenes are cut to the five most newsworthy, back in run order."""
    splits = _every_kind_run()

    monkeypatch.setattr(run_moments, "MAX_MOMENTS", 10)
    assert len(detect_moments(splits, hr_ceiling=150)) == 7

    monkeypatch.setattr(run_moments, "MAX_MOMENTS", 5)
    moments = detect_moments(splits, hr_ceiling=150)

    assert len(moments) == 5
    assert [m["id"] for m in moments] == ["m1", "m2", "m3", "m4", "m5"]
    kms = [m["km_from"] for m in moments]
    assert kms == sorted(kms)
    kinds = {m["kind"] for m in moments}
    assert "ceiling_touch" in kinds
    assert "climb" not in kinds


@pytest.mark.unit
def test_moments_json_serialisable() -> None:
    """Scenes go into a prompt and a JSON column, so no numpy / Decimal leaks."""
    for splits, ceiling in (
        (_ceiling_touch_run(), 150),
        (_long_run_with_walk_breaks(), 150),
        (_every_kind_run(), None),
    ):
        payload = json.dumps(detect_moments(splits, hr_ceiling=ceiling))
        assert json.loads(payload) == detect_moments(splits, hr_ceiling=ceiling)


# --- detect_recurrence ------------------------------------------------------


@pytest.mark.unit
def test_recurrence_counts_same_kind_near_same_km() -> None:
    """The ceiling gets touched around km 4 on 3 of the last 5 easy runs."""
    today = [{"id": "m1", "kind": "ceiling_touch", "km_from": 4, "km_to": 4}]
    previous = [
        {
            "activity_date": "2026-09-16",
            "moments": [{"kind": "ceiling_touch", "km_from": 3, "km_to": 3}],
        },
        {
            "activity_date": "2026-09-13",
            "moments": [{"kind": "ceiling_touch", "km_from": 4, "km_to": 5}],
        },
        {
            "activity_date": "2026-09-10",
            "moments": [{"kind": "walk_break", "km_from": 4, "km_to": 4}],
        },
        {
            "activity_date": "2026-09-07",
            "moments": [{"kind": "ceiling_touch", "km_from": 9, "km_to": 9}],
        },
    ]

    recurrence = detect_recurrence(today, previous)

    assert recurrence == [
        {
            "kind": "ceiling_touch",
            "km": 4,
            "count": 3,
            "of": 5,
            "dates": ["2026-09-16", "2026-09-13"],
        }
    ]


@pytest.mark.unit
def test_recurrence_ignores_single_occurrence() -> None:
    """A one-off scene is not a pattern: km 9 is too far from today's km 4."""
    today = [{"id": "m1", "kind": "ceiling_touch", "km_from": 4, "km_to": 4}]
    previous: list[dict[str, Any]] = [
        {
            "activity_date": "2026-09-16",
            "moments": [{"kind": "ceiling_touch", "km_from": 9, "km_to": 9}],
        },
        {"activity_date": "2026-09-13", "moments": []},
    ]

    assert detect_recurrence(today, previous) == []
