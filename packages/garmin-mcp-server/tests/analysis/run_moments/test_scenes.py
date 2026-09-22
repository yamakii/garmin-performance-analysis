"""Turning points inside a step: the steady detectors and their recurrence.

Calibrated in #1261 against the runs that broke the first cut, re-pinned in
#1268 on real distances (a scene's ``km_from`` is where the athlete was, not
which lap it was recorded under).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from garmin_mcp.analysis import run_moments
from garmin_mcp.analysis.run_moments import detect_moments, detect_recurrence

from .splits import (
    _ceiling_touch_run,
    _every_kind_run,
    _fading_run,
    _four_ceiling_contacts_run,
    _kinds_by_km,
    _long_run_with_walk_breaks,
    _momentary_peak_run,
    _occupied_splits,
    _recovery_run,
    _rows,
    _spans,
    _split,
)

# --- detect_moments ---------------------------------------------------------


@pytest.mark.unit
def test_momentary_peak_is_not_a_ceiling_touch() -> None:
    """9/17: km 1 averages 131 bpm, so its 155 bpm peak is noise, not a touch.

    The spike used to open the scene list and then pollute recurrence
    ("ceiling_touch at km 1 in 3 of 5 runs"). Only km 3-5, where the average
    sits on the ceiling, is contact.
    """
    moments = detect_moments(_momentary_peak_run(), hr_ceiling=150)

    assert 1 not in [
        index
        for moment in moments
        if moment["kind"] == "ceiling_touch"
        for index in _occupied_splits(moment)
    ]
    # Laps 3-5 of a 1 km-per-lap run: km 2 to km 5.
    assert _spans(moments, "ceiling_touch") == [(2, 5)]


@pytest.mark.unit
def test_sustained_contact_with_correction_is_one_scene() -> None:
    """9/18: the touch is km 4-5 and the easing-off is a fact of it, not a scene.

    km 3 peaks at 151 against a 150 ceiling while averaging 147 -- a 1 bpm
    momentary peak. The sustained contact starts at km 4, where the athlete also
    gives back 13 s/km and km 5's average HR stops climbing.
    """
    moments = detect_moments(_ceiling_touch_run(), hr_ceiling=150)

    # Laps 4-5 of a 1 km-per-lap run: km 3 to km 5, named after the road.
    assert _spans(moments, "ceiling_touch") == [(3, 5)]
    touch = next(m for m in moments if m["kind"] == "ceiling_touch")
    assert touch["unit"] == "km"
    assert touch["label_ja"] == "3–5 km"
    assert (touch["split_from"], touch["split_to"]) == (4, 5)
    assert touch["facts"]["corrected_at_km"] == 3
    assert touch["facts"]["corrected_at_split"] == 4
    assert touch["facts"]["pace_drop_s_per_km"] == pytest.approx(12.5, abs=0.6)
    assert touch["facts"]["max_hr"] == 156
    assert "self_correction" not in {m["kind"] for m in moments}
    assert 3 not in _occupied_splits(touch)


@pytest.mark.unit
def test_long_run_keeps_strong_finish() -> None:
    """9/13: the ceiling must not eat all five slots and drop the closing 3 km.

    The day's story is 8:06 -> 7:53 -> 7:41 at HR 148 after 22 km; with four
    ceiling touches and a walk break competing for the cap it used to be lost.
    """
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    assert [(m["kind"], m["km_from"], m["km_to"]) for m in moments] == [
        ("fast_start", 0, 2),
        ("ceiling_touch", 2, 9),
        ("walk_break", 13, 22),
        ("ceiling_touch", 16, 17),
        ("strong_finish", 22, 25),
    ]
    assert moments[1]["facts"]["corrected_at_km"] == 2
    assert moments[2]["facts"]["km_list"] == [13, 19, 21]
    assert moments[2]["facts"]["split_list"] == [14, 20, 22]


@pytest.mark.unit
def test_single_slow_km_is_not_a_fade() -> None:
    """7/31: one slow kilometre before the fastest one is a steady recovery run."""
    moments = detect_moments(_recovery_run(), hr_ceiling=None)

    assert len(moments) == 1
    assert moments[0]["kind"] == "steady"
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (0, 4)


@pytest.mark.unit
def test_fade_requires_the_final_split() -> None:
    """A fade has to reach the finish line, not just dip in the last third."""
    fading = detect_moments(_fading_run(460.0), hr_ceiling=None)
    assert _kinds_by_km(fading)["fade"] == (9, 12)

    recovered = detect_moments(_fading_run(420.0), hr_ceiling=None)
    assert "fade" not in {m["kind"] for m in recovered}


@pytest.mark.unit
def test_scenes_do_not_overlap() -> None:
    """No kilometre belongs to two scenes -- one event, one band on the chart."""
    for splits, ceiling in (
        (_momentary_peak_run(), 150),
        (_ceiling_touch_run(), 150),
        (_long_run_with_walk_breaks(), 150),
        (_recovery_run(), None),
        (_every_kind_run(), 150),
        (_four_ceiling_contacts_run(), 150),
    ):
        moments = detect_moments(splits, hr_ceiling=ceiling)
        claimed = [index for moment in moments for index in _occupied_splits(moment)]
        assert len(claimed) == len(set(claimed)), moments


@pytest.mark.unit
def test_max_two_scenes_per_kind() -> None:
    """Four sustained contacts keep the two longest, so other kinds still fit."""
    moments = detect_moments(_four_ceiling_contacts_run(), hr_ceiling=150)

    assert _spans(moments, "ceiling_touch") == [(4, 7), (14, 18)]


@pytest.mark.unit
def test_fast_start_replaces_start() -> None:
    """Opening 60 s/km faster than the median is a fast start, not a start."""
    splits = _rows(
        [
            (420, 150, 155, 178, 2),
            (420, 148, 153, 178, 2),
            (480, 146, 151, 178, 2),
            (480, 144, 149, 178, 2),
            (480, 142, 147, 178, 2),
            (480, 140, 145, 178, 2),
        ]
    )

    moments = detect_moments(splits, hr_ceiling=None)

    assert moments[0]["kind"] == "fast_start"
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (0, 2)
    assert "start" not in {m["kind"] for m in moments}


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
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (0, 5)
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
    assert walk["facts"]["km_list"] == [13, 19, 21]
    assert (walk["km_from"], walk["km_to"]) == (13, 22)
    assert walk["facts"]["cadence"] == 159
    assert sum(1 for m in moments if m["kind"] == "walk_break") == 1


@pytest.mark.unit
def test_strong_finish_detected_on_long_run() -> None:
    """The closing 3 km at 8:06 -> 7:41 under the ceiling is a strong finish."""
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    finish = next(m for m in moments if m["kind"] == "strong_finish")
    assert (finish["km_from"], finish["km_to"]) == (22, 25)
    assert finish["facts"]["median_pace_s_per_km"] == 510
    assert finish["facts"]["pace_delta_s_per_km"] == 37


@pytest.mark.unit
def test_no_ceiling_means_no_ceiling_scenes() -> None:
    """Without a prescribed ceiling there is nothing to touch or correct to."""
    splits = _ceiling_touch_run()

    with_ceiling = detect_moments(splits, hr_ceiling=150)
    without_ceiling = detect_moments(splits, hr_ceiling=None)

    assert "ceiling_touch" in _kinds_by_km(with_ceiling)
    assert "ceiling_touch" not in {m["kind"] for m in without_ceiling}
    assert not any("corrected_at_km" in m["facts"] for m in without_ceiling)


@pytest.mark.unit
def test_moments_capped_and_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Six scenes are cut to the five most newsworthy, back in run order."""
    splits = _every_kind_run()

    monkeypatch.setattr(run_moments, "MAX_MOMENTS", 10)
    assert len(detect_moments(splits, hr_ceiling=150)) == 6

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


# --- breakdown (#1340) ------------------------------------------------------


@pytest.mark.unit
def test_breakdown_moment_covers_run_end() -> None:
    """The stretch the run never came back from is told as one scene."""
    splits = _rows(
        [(420.0, 140.0, 148.0, 178.0, 2.0)] * 6
        + [(700.0, 110.0, 120.0, 120.0, 2.0)] * 4
    )

    moments = detect_moments(splits, hr_ceiling=None, breakdown_from_km=6.0)

    breakdown = [m for m in moments if m["kind"] == "breakdown"]
    assert len(breakdown) == 1
    assert (breakdown[0]["km_from"], breakdown[0]["km_to"]) == (6.0, 10.0)


@pytest.mark.unit
def test_breakdown_outranks_walk_break() -> None:
    """Walking inside the collapse belongs to that story, not to its own scene."""
    splits = _rows(
        [(420.0, 140.0, 148.0, 178.0, 2.0)] * 6
        + [(900.0, 105.0, 115.0, 100.0, 2.0)] * 4
    )

    moments = detect_moments(splits, hr_ceiling=None, breakdown_from_km=6.0)

    assert "breakdown" in {m["kind"] for m in moments}
    walks = [m for m in moments if m["kind"] == "walk_break"]
    assert all(m["km_from"] < 6.0 for m in walks)


@pytest.mark.unit
def test_no_breakdown_without_a_breakdown_point() -> None:
    """A run that held together is read exactly as before."""
    moments = detect_moments(
        _rows([(420.0, 140.0, 148.0, 178.0, 2.0)] * 10), hr_ceiling=None
    )

    assert all(m["kind"] != "breakdown" for m in moments)
