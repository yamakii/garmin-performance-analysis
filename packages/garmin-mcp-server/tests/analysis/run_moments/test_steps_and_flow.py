"""Steps, the axis they imply, and the series the chart draws (#1268).

Where a scene is drawn (real distance and elapsed time) and what it is called
(a stretch of road, or a step of the session) are decided separately here.
"""

from __future__ import annotations

import json

import pytest

from garmin_mcp.analysis.run_moments import build_flow, build_steps, detect_moments

from .splits import (
    _bookended_long_run,
    _ceiling_touch_run,
    _labels,
    _long_run_with_walk_breaks,
    _rep_session,
    _rows,
    _split,
    _tempo_session,
    _threshold_session,
)

# --- steps and positions ----------------------------------------------------


@pytest.mark.unit
def test_steps_absorb_fragments_in_structured_run() -> None:
    """4/20: a rep recorded as 1.0 + 0.11 km is one 1.11 km step.

    The lap key is pressed a beat after the rep ends, so the raw split is not
    the unit the athlete ran -- the step is.
    """
    steps = build_steps(_threshold_session())

    assert [(s["label_ja"], s["split_from"], s["split_to"]) for s in steps] == [
        ("ウォームアップ", 1, 2),
        ("1本目", 3, 4),
        ("レスト1", 5, 5),
        ("2本目", 6, 7),
        ("クールダウン", 8, 9),
    ]
    rep_one = steps[1]
    assert rep_one["distance_km"] == pytest.approx(1.11)
    assert rep_one["duration_s"] == 360
    assert rep_one["pace_s_per_km"] == pytest.approx(324.3, abs=0.5)
    assert rep_one["avg_hr"] == pytest.approx(170.4, abs=0.1)
    assert rep_one["rep_no"] == 1
    assert rep_one["is_long"] is False


@pytest.mark.unit
def test_single_step_run_has_one_step() -> None:
    """A run whose splits are all ``run`` is one step called 本編."""
    splits = [
        *_rows([(420, 140, 150, 178, 2) for _ in range(5)]),
        _split(6, 365, 148, 152, distance_km=0.014),
        _split(7, 380, 146, 150, distance_km=0.010),
    ]

    steps = build_steps(splits)

    assert len(steps) == 1
    assert steps[0]["label_ja"] == "本編"
    assert steps[0]["is_long"] is True
    assert (steps[0]["split_from"], steps[0]["split_to"]) == (1, 7)


@pytest.mark.unit
def test_role_phase_wins_over_intensity_type() -> None:
    """72 plain runs carry ``INTERVAL`` on every split -- role_phase decides.

    Reading the intensity type first would put a rep story (and a time axis) on
    an ordinary easy run.
    """
    splits = _rows([(420, 140, 150, 178, 2) for _ in range(6)])
    for split in splits:
        split["role_phase"] = "run"
        split["intensity_type"] = "INTERVAL"

    steps = build_steps(splits)

    assert len(steps) == 1
    assert build_flow(splits)["axis"] == "distance"


@pytest.mark.unit
def test_positions_are_cumulative_over_all_splits() -> None:
    """A 50 m fragment still moves the athlete down the road."""
    splits = [
        _split(1, 420, 140, 150),
        _split(2, 360, 142, 151, distance_km=0.05),
        _split(3, 425, 143, 152),
    ]

    segments = build_flow(splits)["segments"]

    assert [segment["split_from"] for segment in segments] == [1, 3]
    assert segments[1]["start_km"] == pytest.approx(1.05)


# --- axis and step scenes ---------------------------------------------------


@pytest.mark.unit
def test_rep_session_uses_time_axis_and_step_labels() -> None:
    """4/20: the reps are the scenes, and a 0.18 km rest needs a time axis."""
    splits = _threshold_session()

    moments = detect_moments(splits, hr_ceiling=None)

    assert build_flow(splits)["axis"] == "time"
    assert {m["unit"] for m in moments} == {"step"}
    assert _labels(moments) == [
        "ウォームアップ",
        "1本目",
        "レスト1",
        "2本目",
        "クールダウン",
    ]
    assert {m["kind"] for m in moments} == {"warmup", "rep", "rest", "cooldown"}
    assert not {"surge", "walk_break"} & {m["kind"] for m in moments}


@pytest.mark.unit
def test_rep_facts_describe_each_rep() -> None:
    """Every rep is read against the first one, and a rest against its rep."""
    moments = detect_moments(_threshold_session(), hr_ceiling=None)

    second = next(m for m in moments if m["label_ja"] == "2本目")
    assert second["facts"]["pace_vs_first_s"] == pytest.approx(-5.7, abs=0.5)
    assert second["facts"]["max_hr_vs_first"] == 6

    rest = next(m for m in moments if m["label_ja"] == "レスト1")
    assert rest["facts"]["hr_drop_bpm"] == 22
    assert rest["t_from_s"] == 960


@pytest.mark.unit
def test_many_reps_collapse_into_work_set() -> None:
    """Five reps plus their rests would bury the bookends, so they merge."""
    moments = detect_moments(_rep_session(5), hr_ceiling=None)

    assert _labels(moments) == ["ウォームアップ", "本編（1〜5本目）", "クールダウン"]
    work_set = moments[1]
    assert work_set["kind"] == "work_set"
    assert len(work_set["facts"]["reps"]) == 5
    assert len(work_set["facts"]["rests"]) == 5
    assert work_set["facts"]["pace_spread_s"] == pytest.approx(4.0, abs=0.5)


@pytest.mark.unit
def test_tempo_run_uses_distance_axis_with_km_scenes() -> None:
    """9/9: a warmup, a 5 km main set read in kilometres, and a cooldown."""
    splits = _tempo_session()

    moments = detect_moments(splits, hr_ceiling=None)

    assert build_flow(splits)["axis"] == "distance"
    assert [(m["kind"], m["unit"]) for m in moments] == [
        ("warmup", "step"),
        ("steady", "km"),
        ("cooldown", "step"),
    ]
    main = moments[1]
    assert main["label_ja"].startswith("本編 ")
    assert main["km_from"] >= 0.93
    assert main["km_to"] <= 5.93


@pytest.mark.unit
def test_steady_run_scene_km_is_cumulative_distance() -> None:
    """A 0.6 km lap shifts every later scene: laps 4-5 are km 2.6-4.6.

    The shipped page drew this run's ceiling touch at "km 4-5" because the
    scene was positioned by lap number (#1268).
    """
    splits = [
        _split(1, 420, 140, 148),
        _split(2, 420, 140, 148, distance_km=0.6),
        _split(3, 420, 140, 148),
        _split(4, 420, 151, 156),
        _split(5, 420, 152, 157),
    ]

    moments = detect_moments(splits, hr_ceiling=150)

    touch = next(m for m in moments if m["kind"] == "ceiling_touch")
    assert touch["split_from"] == 4
    assert touch["km_from"] == pytest.approx(2.6)
    assert touch["km_to"] == pytest.approx(4.6)
    assert touch["label_ja"] == "2.6–4.6 km"


@pytest.mark.unit
def test_walk_break_label_lists_distances() -> None:
    """9/13: the walk breaks are named by where they happened, not by lap."""
    moments = detect_moments(_long_run_with_walk_breaks(), hr_ceiling=150)

    walk = next(m for m in moments if m["kind"] == "walk_break")
    assert walk["facts"]["split_list"] == [14, 20, 22]
    assert walk["facts"]["km_list"] == [13.0, 19.0, 21.0]
    assert walk["label_ja"] == "13・19・21 km 付近"


@pytest.mark.unit
def test_bookended_long_run_keeps_steady_detectors() -> None:
    """WU / CD bookends do not turn a long run into a rep session."""
    splits = _bookended_long_run()

    moments = detect_moments(splits, hr_ceiling=None)

    assert build_flow(splits)["axis"] == "distance"
    assert _labels(moments)[0] == "ウォームアップ"
    assert _labels(moments)[-1] == "クールダウン"
    finish = next(m for m in moments if m["kind"] == "strong_finish")
    assert finish["unit"] == "km"
    assert finish["label_ja"].startswith("本編 ")
    assert (finish["km_from"], finish["km_to"]) == (18, 21)


@pytest.mark.unit
def test_progression_step_replaces_steady_detectors() -> None:
    """A build-up is one scene about the ramp, not five about its kilometres."""
    paces = [480.0, 470.0, 455.0, 440.0, 425.0]
    hrs = [132.0, 138.0, 143.0, 148.0, 152.0]
    splits = _rows(
        [(pace, hr, hr + 6, 178.0, 2.0) for pace, hr in zip(paces, hrs, strict=True)]
    )

    moments = detect_moments(splits, hr_ceiling=None)

    assert [m["kind"] for m in moments] == ["progression"]
    assert moments[0]["unit"] == "km"
    assert moments[0]["label_ja"] == "0–5 km"
    assert len(moments[0]["facts"]["per_km"]) == 5
    assert moments[0]["facts"]["pace_gain_s_per_km"] == 55


# --- flow -------------------------------------------------------------------


@pytest.mark.unit
def test_flow_draws_one_segment_per_short_step() -> None:
    """A short step is drawn whole; a long step is drawn split by split."""
    flow = build_flow(_threshold_session())

    assert [s["step_id"] for s in flow["segments"]] == ["s1", "s2", "s3", "s4", "s5"]
    assert (flow["segments"][1]["start_s"], flow["segments"][1]["end_s"]) == (600, 960)
    assert flow["fragments"] == {"count": 0, "distance_km": 0}
    assert flow["total_km"] == pytest.approx(5.0, abs=0.01)


@pytest.mark.unit
def test_flow_is_json_serialisable() -> None:
    """The page reads the flow straight out of the payload."""
    for splits in (_threshold_session(), _tempo_session(), _ceiling_touch_run()):
        flow = build_flow(splits)
        assert json.loads(json.dumps(flow)) == flow
