"""Tests for deterministic run scene detection (#1249, calibrated in #1261).

The scenes are what the split section is allowed to narrate, so the rules are
pinned against **real split data** from the runs that exposed the first cut's
over-sensitivity: a 5 km run whose km 1 spikes to 155 bpm while averaging 131
(9/17), a short run whose sustained ceiling contact spans two kilometres with a
correction inside it (9/18), a 25 km long run that must not spend all five slots
on the ceiling (9/13), and a 4 km recovery run whose single slow kilometre is
not a fade (7/31).
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


def _rows(rows: list[tuple[float, float, float, float, float]]) -> list[dict[str, Any]]:
    """``(pace, avg_hr, max_hr, cadence, gain)`` tuples -> split rows from km 1."""
    return [
        _split(i, pace, avg_hr, max_hr, cadence=cadence, elevation_gain_m=gain)
        for i, (pace, avg_hr, max_hr, cadence, gain) in enumerate(rows, start=1)
    ]


def _momentary_peak_run() -> list[dict[str, Any]]:
    """The 9/17 run: km 1 peaks at 155 bpm while averaging 131 (ceiling 150)."""
    return _rows(
        [
            (423, 131, 155, 176, 2),
            (411, 144, 149, 181, 2),
            (416, 149, 155, 180, 2),
            (424, 150, 154, 181, 2),
            (421, 148, 156, 178, 2),
        ]
    )


def _ceiling_touch_run() -> list[dict[str, Any]]:
    """The 9/18 run: sustained contact at km 4-5, eased off at km 4."""
    return _rows(
        [
            (413, 129, 140, 177, 2),
            (407, 145, 149, 183, 2),
            (419, 147, 151, 184, 2),
            (432, 148, 156, 183, 2),
            (413, 148, 155, 178, 2),
        ]
    )


def _recovery_run() -> list[dict[str, Any]]:
    """The 7/31 recovery run: one slow km 3, then the fastest kilometre."""
    return _rows(
        [
            (485, 116, 126, 172, 2),
            (479, 128, 134, 174, 2),
            (497, 132, 137, 172, 2),
            (476, 135, 145, 170, 2),
        ]
    )


def _long_run_with_walk_breaks() -> list[dict[str, Any]]:
    """The 9/13 long run: 25 km, walk breaks at km 14 / 20 / 22, median 510."""
    paces = [
        446, 466, 514, 521, 540, 539, 528, 513, 517, 510, 486, 491, 485,
        530, 532, 505, 482, 508, 509, 563, 516, 538, 486, 473, 461,
    ]  # fmt: skip
    avg_hrs = [
        136, 148, 150, 150, 153, 149, 148, 149, 148, 142, 145, 146, 148,
        142, 140, 143, 148, 143, 144, 142, 143, 141, 147, 148, 148,
    ]  # fmt: skip
    max_hrs = [
        152, 152, 156, 154, 158, 154, 152, 155, 160, 152, 149, 156, 152,
        159, 151, 153, 156, 154, 149, 149, 147, 150, 152, 151, 152,
    ]  # fmt: skip
    cadences = [
        179, 181, 181, 178, 181, 180, 180, 183, 172, 179, 178, 176, 176,
        165, 172, 176, 177, 176, 177, 159, 177, 166, 179, 181, 181,
    ]  # fmt: skip
    return _rows(
        [
            (pace, avg_hr, max_hr, cadence, 3.0)
            for pace, avg_hr, max_hr, cadence in zip(
                paces, avg_hrs, max_hrs, cadences, strict=True
            )
        ]
    )


def _every_kind_run() -> list[dict[str, Any]]:
    """12 splits deliberately firing six scenes (median pace 425 s/km).

    km 1-2 fast start, km 4-5 climb, km 5-6 ceiling touch, km 8 walk break,
    km 9 surge, km 10-12 fade.
    """
    return _rows(
        [
            (400, 130, 140, 176, 2),
            (402, 138, 145, 176, 3),
            (425, 143, 147, 178, 2),
            (425, 143, 147, 176, 18),
            (428, 150, 156, 175, 20),
            (445, 149, 154, 174, 5),
            (420, 143, 147, 176, 2),
            (550, 138, 145, 160, 2),
            (412, 144, 148, 176, 3),
            (445, 146, 148, 175, 3),
            (450, 147, 149, 175, 3),
            (455, 147, 149, 174, 3),
        ]
    )


def _four_ceiling_contacts_run() -> list[dict[str, Any]]:
    """20 flat kilometres with four separate sustained contacts (ceiling 150).

    km 2 (1 split), km 5-7 (3), km 11-12 (2), km 15-18 (4); every gap is wide
    enough that ``MERGE_GAP_SPLITS`` cannot bridge it.
    """
    contacts = {2, 5, 6, 7, 11, 12, 15, 16, 17, 18}
    return _rows(
        [
            (500.0, 151.0 if km in contacts else 140.0, 156.0, 178.0, 2.0)
            for km in range(1, 21)
        ]
    )


def _fading_run(final_pace: float) -> list[dict[str, Any]]:
    """Nine kilometres at 7:00/km, then a closing stretch that lets go."""
    paces = [420.0] * 9 + [450.0, 455.0, final_pace]
    return _rows(
        [(pace, 140.0 + km, 150.0, 178.0, 2.0) for km, pace in enumerate(paces)]
    )


def _kinds_by_km(moments: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """``{kind: (km_from, km_to)}`` for readable assertions on unique kinds."""
    return {m["kind"]: (m["km_from"], m["km_to"]) for m in moments}


def _spans(moments: list[dict[str, Any]], kind: str) -> list[tuple[int, int]]:
    """Every ``(km_from, km_to)`` of one kind, in run order."""
    return [(m["km_from"], m["km_to"]) for m in moments if m["kind"] == kind]


def _occupied_km(moment: dict[str, Any]) -> list[int]:
    """The kilometres a scene owns (``km_list`` for walk breaks, else its span)."""
    km_list = moment["facts"].get("km_list")
    if km_list:
        return [int(km) for km in km_list]
    return list(range(moment["km_from"], moment["km_to"] + 1))


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
        km
        for moment in moments
        if moment["kind"] == "ceiling_touch"
        for km in _occupied_km(moment)
    ]
    assert _spans(moments, "ceiling_touch") == [(3, 5)]


@pytest.mark.unit
def test_sustained_contact_with_correction_is_one_scene() -> None:
    """9/18: the touch is km 4-5 and the easing-off is a fact of it, not a scene.

    km 3 peaks at 151 against a 150 ceiling while averaging 147 -- a 1 bpm
    momentary peak. The sustained contact starts at km 4, where the athlete also
    gives back 13 s/km and km 5's average HR stops climbing.
    """
    moments = detect_moments(_ceiling_touch_run(), hr_ceiling=150)

    assert _spans(moments, "ceiling_touch") == [(4, 5)]
    touch = next(m for m in moments if m["kind"] == "ceiling_touch")
    assert touch["facts"]["corrected_at_km"] == 4
    assert touch["facts"]["pace_drop_s_per_km"] == pytest.approx(12.5, abs=0.6)
    assert touch["facts"]["max_hr"] == 156
    assert "self_correction" not in {m["kind"] for m in moments}
    assert 3 not in _occupied_km(touch)


@pytest.mark.unit
def test_long_run_keeps_strong_finish() -> None:
    """9/13: the ceiling must not eat all five slots and drop the closing 3 km.

    The day's story is 8:06 -> 7:53 -> 7:41 at HR 148 after 22 km; with four
    ceiling touches and a walk break competing for the cap it used to be lost.
    """
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    assert [(m["kind"], m["km_from"], m["km_to"]) for m in moments] == [
        ("fast_start", 1, 2),
        ("ceiling_touch", 3, 9),
        ("walk_break", 14, 22),
        ("ceiling_touch", 17, 17),
        ("strong_finish", 23, 25),
    ]
    assert moments[1]["facts"]["corrected_at_km"] == 3
    assert moments[2]["facts"]["km_list"] == [14, 20, 22]


@pytest.mark.unit
def test_single_slow_km_is_not_a_fade() -> None:
    """7/31: one slow kilometre before the fastest one is a steady recovery run."""
    moments = detect_moments(_recovery_run(), hr_ceiling=None)

    assert len(moments) == 1
    assert moments[0]["kind"] == "steady"
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (1, 4)


@pytest.mark.unit
def test_fade_requires_the_final_split() -> None:
    """A fade has to reach the finish line, not just dip in the last third."""
    fading = detect_moments(_fading_run(460.0), hr_ceiling=None)
    assert _kinds_by_km(fading)["fade"] == (10, 12)

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
        claimed = [km for moment in moments for km in _occupied_km(moment)]
        assert len(claimed) == len(set(claimed)), moments


@pytest.mark.unit
def test_max_two_scenes_per_kind() -> None:
    """Four sustained contacts keep the two longest, so other kinds still fit."""
    moments = detect_moments(_four_ceiling_contacts_run(), hr_ceiling=150)

    assert _spans(moments, "ceiling_touch") == [(5, 7), (15, 18)]


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
    assert (moments[0]["km_from"], moments[0]["km_to"]) == (1, 2)
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
