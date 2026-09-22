"""Deterministic *scene* detection for a single run (pure, no I/O) -- #1249,
#1261, #1268.

The split section used to narrate every kilometre ("全スプリット例外なく"), which
is a numeric readout the table already shows. The redesign keeps prose only for
**how the run unfolded**: 2-5 turning points. This module produces those turning
points *deterministically* from the split rows, so the LLM's job shrinks to
selecting and explaining them -- it cannot invent a scene, because a merge guard
checks the ``moment_id``s it cites against :func:`detect_moments` output.

Four functions, all pure and JSON-serialisable:

- :func:`build_steps` -- one run's split rows -> its steps (warmup / reps /
  rests / main set / cooldown), fragments absorbed.
- :func:`build_flow` -- the series the chart draws, plus the axis it is drawn
  on. One fragment rule for pace and heart rate alike.
- :func:`detect_moments` -- one run's split rows -> at most ``MAX_MOMENTS``
  scenes, ordered by position in the run.
- :func:`detect_recurrence` -- today's scenes plus the previous same-family runs
  -> the kinds that keep happening at the same place in the run.

**Where a scene is drawn and what it is called are two different things**
(#1268). The first cut returned ``split_index`` as ``km_from``, so a run with a
0.11 km fragment or a manual lap drew its scenes at the wrong place and named
them after lap numbers. Now:

* **Position** is a real continuous quantity, cumulative over *every* split:
  ``km_from`` / ``km_to`` (distance) and ``t_from_s`` / ``t_to_s`` (elapsed
  time). Fragments count for positions -- they are part of the run.
* **Name** (``label_ja``, ``unit``) is the unit the athlete thinks in. A steady
  run is narrated in kilometres ("3–5 km"); a rep session is narrated by its
  steps ("1本目", "レスト1"), because one rep can be recorded as two splits and
  a 120 s rest covers 0.18 km -- invisible on a distance axis.

Design notes that are easy to get wrong when editing. Every one of them is a
correction the earlier cuts needed once they met real activities (#1261, #1268):

* **``role_phase`` is primary, ``intensity_type`` only a fallback.** 72 plain
  runs carry ``intensity_type = INTERVAL`` on every split; reading that as rep
  structure would put an interval story on an easy run.
* **A momentary peak is not a ceiling touch.** Every kilometre has an HR spike;
  the 9/17 run peaked at 155 bpm inside a kilometre averaging 131 against a 150
  ceiling. Contact has to be *sustained* (:func:`_is_ceiling_touch`), or the
  scene list fills with spikes and :func:`detect_recurrence` reports a habit
  that never happened.
* **Scenes are built per kind, then de-conflicted.** One kilometre can satisfy
  several rules at once (a ceiling touch on a climb). Each kind gets its own
  qualifying splits -- same-kind stretches separated by at most
  ``MERGE_GAP_SPLITS`` merge into one scene -- and afterwards
  :func:`_resolve_overlaps` hands every split to the highest-priority scene
  claiming it, trimming the losers. One event never draws two bands.
* **The end of the run must survive the cap.** A 25 km run that spends its
  middle on the ceiling would otherwise fill all five slots there and drop the
  story of the day (the closing 3 km). ``MAX_PER_KIND`` bounds a single kind
  before the global ``MAX_MOMENTS`` cut.
* **Fragments are dropped before anything is measured** *inside a long step*.
  Manual lap presses leave 5-11 m laps whose pace is a measurement artifact (as
  fast as 4:04/km), which would otherwise fake a surge or a ceiling touch. The
  threshold is ``MIN_SPLIT_KM`` from ``form_baseline.split_filter`` so this
  module and the form baseline cannot drift apart. Inside a *short* step a
  fragment is absorbed instead: the 1.0 + 0.11 km rep is one 1.11 km rep.
* **Walk laps do not move the run median.** The median pace every rule is
  measured against is taken over *running* splits only
  (``MAX_RUNNING_PACE_S_PER_KM``); a run with several walk breaks would
  otherwise raise its own bar and hide those very breaks.
* Every threshold is a module-level constant so tests (and future calibration)
  can override it without touching the rules.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from garmin_mcp.analysis.derivations import detect_progression_session
from garmin_mcp.form_baseline.split_filter import (
    MAX_RUNNING_PACE_S_PER_KM,
    MIN_SPLIT_KM,
)

# --- Steps ------------------------------------------------------------------

# The roles a split can carry, in the order a run executes them. ``stride``
# comes only from ``role_phase`` (#1296): Garmin records a stride as ``ACTIVE``
# like the jog around it, so no intensity type maps to it.
ROLES: tuple[str, ...] = ("warmup", "run", "stride", "recovery", "cooldown")

# The steps an easy-run rule (the HR ceiling above all) is judged on (#1297).
# Strides are short and fast by design, and the jog after one is where heart
# rate comes back down -- neither is the easy running the ceiling guards.
_JOG_ROLES: frozenset[str] = frozenset({"warmup", "run", "cooldown"})

# Scene kinds that never make a recurrence: they describe the run's shape, not
# something that keeps happening to the athlete. Strides are *prescribed*, so
# "strides again at km 5" is the plan being followed, not a habit (#1297).
_NON_RECURRING_KINDS: frozenset[str] = frozenset({"start", "steady", "strides"})

# A step long enough to be narrated kilometre by kilometre instead of as one
# block: three splits that are not fragments.
LONG_STEP_MIN_SPLITS = 3

# A lap without a workout step index this short is the edge of a watch
# workout -- the seconds before the stop button after its last step -- and
# joins the step next to it; a longer one is running of its own (#1324).
# Observed tails: 43 s / 0.118 km, 36 s / 0.071 km, 2 s / 0.006 km.
UNINDEXED_EDGE_MAX_S = 60.0

# A rep session needs at least this many ``run`` steps alternating with at
# least this many ``recovery`` steps. Below that the run is a plain run with
# bookends, narrated on a distance axis.
REP_MIN_RUN_STEPS = 2
REP_MIN_RECOVERY_STEPS = 1

# Garmin ``intensity_type`` -> role, used only when ``role_phase`` is null.
_INTENSITY_ROLES: dict[str, str] = {
    "WARMUP": "warmup",
    "INTERVAL": "run",
    "ACTIVE": "run",
    "RECOVERY": "recovery",
    "REST": "recovery",
    "COOLDOWN": "cooldown",
}

# role -> (long label, chart label) for the steps that are not numbered reps.
_ROLE_LABELS: dict[str, tuple[str, str]] = {
    "warmup": ("ウォームアップ", "アップ"),
    "run": ("本編", "本編"),
    "cooldown": ("クールダウン", "ダウン"),
}

# --- Scene thresholds -------------------------------------------------------

# A split counts as a surge when it beats the run median by this margin (8 s/km
# is well outside GPS pace noise).
SURGE_S_PER_KM = 8.0

# A correction is a visible easing-off: the athlete gives back at least this
# much pace at (or right beside) a ceiling touch. It is not a scene of its own
# -- it is a fact of the touch it answers (#1261).
CORRECTION_S_PER_KM = 10.0

# Sustained contact with the prescribed ceiling. Either the kilometre *averages*
# at or above it, or its peak clears it by ``CEILING_PEAK_MARGIN_BPM`` while the
# average is already within ``CEILING_NEAR_BPM`` of it.
CEILING_PEAK_MARGIN_BPM = 3.0
CEILING_NEAR_BPM = 2.0

# A fast start is the opening 1-2 kilometres run this much faster than the run
# median -- the classic "went out hot" the rest of the run pays for.
FAST_START_S_PER_KM = 20.0
FAST_START_MAX_SPLITS = 2

# Two same-kind stretches separated by at most this many non-qualifying splits
# are one scene: a single kilometre dipping under the ceiling does not end the
# time spent on it.
MERGE_GAP_SPLITS = 1

# Below this cadence the athlete is walking, not running (running laps sit at
# ~175 spm, walk laps at ~65-115 spm; 170 leaves room for a tired shuffle).
WALK_CADENCE_SPM = 170.0

# A walk break must also cost pace against the run median -- a low-cadence but
# on-pace split is a stride-length change, not a break.
WALK_PACE_S_PER_KM = 15.0

# Metres of gain within one kilometre that make the climb the story of that km.
CLIMB_M_PER_KM = 15.0

# Last-third pace loss (against the first-third median) that counts as a fade,
# but only while heart rate holds -- see :func:`_is_fade`. A fade also has to
# *reach the finish*: one slow kilometre followed by the fastest one of the run
# is a dip, not a fade.
FADE_S_PER_KM = 15.0
FADE_MIN_SPLITS = 2
FADE_SHORT_RUN_SPLITS = 8

# A strong finish looks at the last ``STRONG_FINISH_SPLITS`` splits, or just the
# final one on runs shorter than ``STRONG_FINISH_SHORT_RUN_KM`` (where three
# kilometres would be half the run).
STRONG_FINISH_SPLITS = 3
STRONG_FINISH_SHORT_RUN_KM = 8.0
# Without a prescribed ceiling, "contained HR" means not above the run's own
# heart-rate distribution at this percentile.
STRONG_FINISH_HR_PERCENTILE = 90.0

# At most this many scenes of one kind, and this many scenes in total; the rest
# are dropped by :data:`_PRIORITY`.
MAX_PER_KIND = 2
MAX_MOMENTS = 5

# --- Recurrence -------------------------------------------------------------

# How many previous same-intensity-family runs to look back over.
RECURRENCE_LOOKBACK = 4
# Two scenes are "the same place in the run" within this many kilometres.
RECURRENCE_KM_TOLERANCE = 1.0
# A pattern is only worth mentioning once it has happened on this many runs.
RECURRENCE_MIN_COUNT = 2

# Most-to-least newsworthy, in tiers: kinds inside a tier rank equally (a fade
# and a strong finish are both "how it ended"). Decides which scene keeps a
# contested split and which scenes survive the ``MAX_MOMENTS`` cap.
_PRIORITY: tuple[tuple[str, ...], ...] = (
    ("ceiling_touch",),
    ("breakdown", "fade", "strong_finish", "progression"),
    ("work_set", "rep", "strides"),
    ("walk_break",),
    ("steady", "main"),
    ("rest", "warmup", "cooldown"),
    ("fast_start",),
    ("surge",),
    ("climb",),
    ("start",),
)

_RANK: dict[str, int] = {
    kind: rank for rank, tier in enumerate(_PRIORITY) for kind in tier
}

# A candidate scene before it becomes a dict: its kind and the indices of the
# valid splits it covers.
_Candidate = tuple[str, list[int]]


def build_steps(splits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group a run's splits into the steps the athlete ran.

    A step is a maximal run of consecutive splits sharing a ``role_phase``
    (``intensity_type`` is consulted only when ``role_phase`` is null). A
    fragment is *absorbed* into its step, so the 1.0 + 0.11 km rep of the 4/20
    threshold session is one 1.11 km / 360 s step.

    Args:
        splits: The run's split rows, in order (see :func:`detect_moments` for
            the fields read).

    Returns:
        ``[{"id": "s1", "role", "label_ja", "short_ja", "rep_no", "split_from",
        "split_to", "start_km", "end_km", "start_s", "end_s", "distance_km",
        "duration_s", "pace_s_per_km", "avg_hr", "max_hr", "is_long"}]`` in run
        order. ``avg_hr`` is time-weighted; ``rep_no`` is ``None`` outside a rep
        session.
    """
    return [_public_step(step) for step in _steps(_positioned_splits(splits))]


def build_flow(splits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The series the chart draws, and the axis it is drawn on.

    The report ships what the chart draws so pace and heart rate cannot apply
    different fragment rules -- the shipped page dropped the sub-0.4 km splits
    from the pace line while still plotting them on the HR line (#1268).

    Args:
        splits: The run's split rows, in order.

    Returns:
        ``{"axis": "distance" | "time", "total_km", "total_s", "segments",
        "steps", "fragments"}``. ``segments`` is one entry per drawn split
        inside a long step (and inside a single-step run) and one entry per
        *whole* short step; ``fragments`` counts the splits that are neither
        drawn nor absorbed.
    """
    positioned = _positioned_splits(splits)
    steps = _steps(positioned)
    single = len(steps) == 1

    segments: list[dict[str, Any]] = []
    fragment_rows: list[dict[str, Any]] = []
    for step in steps:
        rows = step["rows"]
        if not (single or step["is_long"]):
            segments.append(_segment(step, rows))
            continue
        for row in rows:
            if _is_drawable(row):
                segments.append(_segment(step, [row]))
            else:
                fragment_rows.append(row)

    return {
        "axis": "time" if _has_rep_structure(steps) else "distance",
        "total_km": _round3(sum(row["distance_km"] for row in positioned)),
        "total_s": _round1(sum(row["duration_s"] for row in positioned)),
        "segments": segments,
        "steps": [_public_step(step) for step in steps],
        "fragments": {
            "count": len(fragment_rows),
            "distance_km": _round3(sum(row["distance_km"] for row in fragment_rows)),
        },
    }


def detect_moments(
    splits: Sequence[Mapping[str, Any]],
    *,
    hr_ceiling: int | None,
    prescription: Mapping[str, Any] | None = None,
    breakdown_from_km: float | None = None,
) -> list[dict[str, Any]]:
    """Detect the turning points of one run.

    Args:
        splits: The run's split rows, in order. Each row is read for
            ``split_index``, ``distance_km``, ``pace_s_per_km``, ``avg_hr``,
            ``max_hr``, ``cadence``, ``elevation_gain_m``, ``role_phase``,
            ``intensity_type`` and the timing fields ``start_s`` / ``end_s`` /
            ``duration_s``; missing or ``None`` fields simply disable the rules
            that need them.
        hr_ceiling: The prescription's heart-rate ceiling, or ``None`` when the
            run was not prescribed one. Without it no ``ceiling_touch`` scene
            can exist.
        prescription: The day's prescription row, consulted only to let a
            prescribed build-up count as a ``progression`` on its heart-rate
            ramp alone.
        breakdown_from_km: Where ``analysis.purpose_outcome`` found the run
            stopped delivering its purpose, or ``None``. The kilometres from
            there to the finish become one ``breakdown`` scene, which outranks
            the walk breaks and slow kilometres inside it: the story is the run
            coming apart, not each symptom (#1340).

    Returns:
        ``[{"id": "m1", "kind", "unit", "label_ja", "km_from", "km_to",
        "t_from_s", "t_to_s", "split_from", "split_to", "step_id", "facts"}]``
        in run order, ids renumbered ``m1..mN`` with ``N <= MAX_MOMENTS``.
        Scenes never share a split. ``unit`` is ``"km"`` for a scene drawn
        inside a long step (``kind`` one of ``start``, ``fast_start``,
        ``surge``, ``ceiling_touch``, ``walk_break``, ``climb``, ``fade``,
        ``breakdown``, ``strong_finish``, ``progression``, ``steady``) and
        ``"step"`` for a
        scene that *is* a step (``kind`` one of ``warmup``, ``rep``, ``rest``,
        ``main``, ``cooldown``, ``work_set``, ``strides``). A block of strides
        and the jogs between them is one ``strides`` scene (#1297), and a
        ``ceiling_touch`` is only ever looked for on the jog (``warmup`` /
        ``run`` / ``cooldown`` steps). JSON-serialisable throughout; no valid
        split returns ``[]``.
    """
    positioned = _positioned_splits(splits)
    if not positioned:
        return []
    steps = _steps(positioned)
    single = len(steps) == 1
    blocks = {block[0]["id"]: block for block in _strides_blocks(steps)}
    in_block = {step["id"] for block in blocks.values() for step in block}

    scenes: list[dict[str, Any]] = []
    for step in steps:
        if step["id"] in blocks:
            strides = _strides_scene(blocks[step["id"]])
            if strides is not None:
                scenes.append(strides)
            continue
        if step["id"] in in_block:
            continue
        if single or step["is_long"]:
            scenes.extend(
                _km_scenes(
                    step,
                    hr_ceiling=hr_ceiling if step["role"] in _JOG_ROLES else None,
                    prescription=prescription,
                    named=not single,
                    breakdown_from_km=breakdown_from_km,
                )
            )
        else:
            scenes.append(_step_scene(step, steps))

    scenes = _collapse_work_set(scenes, steps)
    scenes.sort(key=lambda scene: (scene["split_from"], scene["split_to"]))
    if len(scenes) > MAX_MOMENTS:
        scenes = _cap_scenes(scenes)
    return _number(scenes)


def detect_recurrence(
    today: Sequence[Mapping[str, Any]],
    previous_runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Find today's scenes that keep recurring at the same point of the run.

    A scene becomes a coaching observation only once it is a habit: "the HR
    ceiling gets touched around km 4 again" is worth saying, a single touch is
    not. A kilometre scene matches on its real distance into the run; a step
    scene matches on ``(kind, rep_no)`` -- "the 3rd rep is where it goes".

    Args:
        today: Today's scenes, as returned by :func:`detect_moments`.
        previous_runs: ``[{"activity_date": "YYYY-MM-DD", "moments": [...]}]``
            for the previous runs of the same intensity family, **newest
            first**. Only the first ``RECURRENCE_LOOKBACK`` are considered.

    Returns:
        ``[{"kind", "km", "count", "of", "dates"}]`` for the kinds occurring on
        at least ``RECURRENCE_MIN_COUNT`` runs (today included), where ``km`` is
        today's ``km_from``, ``of`` is the number of runs examined and ``dates``
        are the previous runs that matched. Sorted by ``count`` descending, then
        by ``km``.
    """
    lookback = list(previous_runs[:RECURRENCE_LOOKBACK])
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()

    for moment in today:
        kind = str(moment.get("kind") or "")
        if not kind or kind in _NON_RECURRING_KINDS:
            continue
        km = _round(_as_float(moment.get("km_from")) or 0.0)
        key = (kind, moment.get("rep_no") if _is_step_scene(moment) else km)
        if key in seen:
            continue
        seen.add(key)

        dates = [
            str(run.get("activity_date"))
            for run in lookback
            if _run_has_moment_near(run, moment)
        ]
        count = 1 + len(dates)
        if count < RECURRENCE_MIN_COUNT:
            continue
        results.append(
            {
                "kind": kind,
                "km": km,
                "count": count,
                "of": 1 + len(lookback),
                "dates": dates,
            }
        )

    results.sort(key=lambda entry: (-entry["count"], entry["km"]))
    return results


# --- Split preparation ------------------------------------------------------


def _positioned_splits(
    splits: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Every split with its real position in the run, fragments included.

    Positions are cumulative over *all* splits -- a 0.05 km fragment still
    moves the athlete 50 m down the road, so dropping it here would shift every
    later scene. Elapsed time is accumulated from each split's own duration
    (``end_s - start_s`` when the device recorded them, else
    ``duration_s``, else ``distance * pace``), which keeps the time axis
    contiguous across a paused lap.
    """
    rows: list[dict[str, Any]] = []
    cumulative_km = 0.0
    cumulative_s = 0.0
    for split in splits:
        distance = _as_float(split.get("distance_km")) or 0.0
        duration = _split_duration(split, distance)
        row = dict(split)
        row["distance_km"] = distance
        row["duration_s"] = duration
        row["role"] = _role(split)
        row["start_km"] = _round3(cumulative_km)
        row["end_km"] = _round3(cumulative_km + distance)
        row["start_s"] = _round1(cumulative_s)
        row["end_s"] = _round1(cumulative_s + duration)
        rows.append(row)
        cumulative_km += distance
        cumulative_s += duration
    return rows


def _split_duration(split: Mapping[str, Any], distance: float) -> float:
    """How long one split took, from whichever timing the row carries."""
    start = _as_float(split.get("start_s"))
    end = _as_float(split.get("end_s"))
    if start is not None and end is not None and end > start:
        return end - start
    duration = _as_float(split.get("duration_s"))
    if duration is not None and duration > 0:
        return duration
    pace = _as_float(split.get("pace_s_per_km"))
    return distance * pace if pace and pace > 0 else 0.0


def _role(split: Mapping[str, Any]) -> str:
    """The split's role: ``role_phase`` first, ``intensity_type`` as fallback.

    72 plain runs carry ``intensity_type = INTERVAL`` on every split, so the
    intensity type alone would read an easy run as a rep session (#1268).
    """
    role_phase = str(split.get("role_phase") or "").strip().lower()
    if role_phase in ROLES:
        return role_phase
    intensity = str(split.get("intensity_type") or "").strip().upper()
    return _INTENSITY_ROLES.get(intensity, "run")


def _is_drawable(row: Mapping[str, Any]) -> bool:
    """Whether a split is a measurement, not a manual-lap artifact."""
    pace = _as_float(row.get("pace_s_per_km"))
    return (row["distance_km"] or 0.0) >= MIN_SPLIT_KM and pace is not None and pace > 0


# --- Steps ------------------------------------------------------------------


def _steps(positioned: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Consecutive same-role splits as steps, labelled in the run's own unit.

    A change of ``workout_step_index`` also starts a new step (#1297): runs
    recorded before the stride roles existed carry ``run`` on the jog *and* on
    the first stride, and only the watch's step index tells them apart. Runs
    without a structured workout carry no index, so nothing changes for them.
    """
    groups: list[list[dict[str, Any]]] = []
    for row in positioned:
        if groups and _same_step(groups[-1][-1], row):
            groups[-1].append(dict(row))
        else:
            groups.append([dict(row)])

    steps = [_step(rows, number) for number, rows in enumerate(groups, start=1)]
    _label_steps(steps)
    return steps


def _same_step(previous: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """Whether ``row`` continues the step ``previous`` belongs to.

    Two different step indices start a new step. A *short* lap without an
    index is not a step of its own: the lap between a watch workout's end and
    the stop button carries none, and splitting on it turned a one-step run
    into 本編 + 本編 over a 2-43 s tail (#1324). A long one is running the
    workout did not cover (a jog home after the cool-down), so it stays
    separate rather than padding the last step.
    """
    if previous["role"] != row["role"]:
        return False
    before = previous.get("workout_step_index")
    after = row.get("workout_step_index")
    if before is None and after is None:
        return True
    if before is None:
        return _is_short_unindexed(previous)
    if after is None:
        return _is_short_unindexed(row)
    return bool(before == after)


def _is_short_unindexed(row: Mapping[str, Any]) -> bool:
    """A lap without a step index short enough to be a workout's edge.

    Timed laps are judged by ``UNINDEXED_EDGE_MAX_S``; a lap without a
    duration falls back to ``MIN_SPLIT_KM`` (a fragment).
    """
    duration = _as_float(row.get("duration_s"))
    if duration is not None:
        return duration <= UNINDEXED_EDGE_MAX_S
    distance = _as_float(row.get("distance_km"))
    return distance is not None and distance < MIN_SPLIT_KM


def _step(rows: list[dict[str, Any]], number: int) -> dict[str, Any]:
    """One step and its aggregates (fragments absorbed, HR time-weighted)."""
    distance = sum(row["distance_km"] for row in rows)
    duration = sum(row["duration_s"] for row in rows)
    return {
        "id": f"s{number}",
        "role": rows[0]["role"],
        "label_ja": "",
        "short_ja": "",
        "rep_no": None,
        "split_from": _split_index(rows[0]),
        "split_to": _split_index(rows[-1]),
        "start_km": rows[0]["start_km"],
        "end_km": rows[-1]["end_km"],
        "start_s": rows[0]["start_s"],
        "end_s": rows[-1]["end_s"],
        "distance_km": _round3(distance),
        "duration_s": _round1(duration),
        "pace_s_per_km": _round(duration / distance) if distance > 0 else None,
        "avg_hr": _weighted_hr(rows),
        "max_hr": _max_hr(rows),
        "is_long": sum(1 for row in rows if row["distance_km"] >= MIN_SPLIT_KM)
        >= LONG_STEP_MIN_SPLITS,
        "rows": rows,
    }


def _label_steps(steps: list[dict[str, Any]]) -> None:
    """Name every step in the unit the athlete thinks in."""
    reps = _has_rep_structure(steps)
    in_block = _strides_block_ids(steps)
    rep_no = 0
    rest_no = 0
    stride_no = 0
    for step in steps:
        role = step["role"]
        if role == "stride":
            stride_no += 1
            step["label_ja"] = f"流し{stride_no}本目"
            step["short_ja"] = "流し"
        elif role == "recovery" and step["id"] in in_block:
            step["label_ja"] = f"流し{stride_no}本目のつなぎ"
            step["short_ja"] = "R"
        elif role == "run" and reps:
            rep_no += 1
            step["rep_no"] = rep_no
            step["label_ja"] = f"{rep_no}本目"
            step["short_ja"] = f"{rep_no}本目"
        elif role == "recovery":
            rest_no += 1
            step["label_ja"] = f"レスト{rest_no}" if reps else "リカバリー"
            step["short_ja"] = "R"
        else:
            label, short = _ROLE_LABELS.get(role, ("本編", "本編"))
            step["label_ja"] = label
            step["short_ja"] = short


def _has_rep_structure(steps: Sequence[Mapping[str, Any]]) -> bool:
    """Whether ``run`` and ``recovery`` steps alternate -- a rep session.

    Two run steps around a rest is the smallest thing worth narrating rep by
    rep; anything less is a plain run whose natural unit is the kilometre.

    Strides and the jogs between them do not count (#1297): an easy run with
    strides is a jog read in kilometres, not an interval session -- and the
    jog either side of the strides block would otherwise pass for two reps.
    """
    in_block = _strides_block_ids(steps)
    counted = [step for step in steps if step["id"] not in in_block]
    runs = sum(1 for step in counted if step["role"] == "run")
    rests = sum(1 for step in counted if step["role"] == "recovery")
    return runs >= REP_MIN_RUN_STEPS and rests >= REP_MIN_RECOVERY_STEPS


def _strides_blocks(
    steps: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Each block of strides: a stride step plus every stride / jog after it.

    A block opens on a ``stride`` step and runs over the consecutive
    ``stride`` and ``recovery`` steps that follow, so the jog after the last
    stride (its recovery) belongs to the block too. A recovery *before* the
    first stride is an ordinary rest, not part of the strides.
    """
    blocks: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for step in steps:
        role = step["role"]
        if role == "stride" or (current and role == "recovery"):
            current.append(step)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _strides_block_ids(steps: Sequence[Mapping[str, Any]]) -> set[str]:
    """Ids of every step inside a strides block."""
    return {str(step["id"]) for block in _strides_blocks(steps) for step in block}


def _public_step(step: Mapping[str, Any]) -> dict[str, Any]:
    """The step without its rows -- what the payload carries."""
    return {key: value for key, value in step.items() if key != "rows"}


def _segment(
    step: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """One drawn segment: a split of a long step, or a whole short step."""
    distance = sum(row["distance_km"] for row in rows)
    duration = sum(row["duration_s"] for row in rows)
    return {
        "split_from": _split_index(rows[0]),
        "split_to": _split_index(rows[-1]),
        "step_id": step["id"],
        "start_km": rows[0]["start_km"],
        "end_km": rows[-1]["end_km"],
        "start_s": rows[0]["start_s"],
        "end_s": rows[-1]["end_s"],
        "pace_s_per_km": _round(duration / distance) if distance > 0 else None,
        "avg_hr": _weighted_hr(rows),
        "max_hr": _max_hr(rows),
    }


def _weighted_hr(rows: Sequence[Mapping[str, Any]]) -> float | int | None:
    """Time-weighted average heart rate over the rows that recorded one."""
    pairs = [
        (hr, row["duration_s"])
        for row in rows
        if (hr := _as_float(row.get("avg_hr"))) is not None
    ]
    weight = sum(duration for _, duration in pairs)
    if not pairs:
        return None
    if weight <= 0:
        return _round(sum(hr for hr, _ in pairs) / len(pairs))
    return _round(sum(hr * duration for hr, duration in pairs) / weight)


def _max_hr(rows: Sequence[Mapping[str, Any]]) -> float | int | None:
    """Peak heart rate over the rows that recorded one."""
    values = [h for h in (_as_float(row.get("max_hr")) for row in rows) if h]
    return _round(max(values)) if values else None


def _split_index(row: Mapping[str, Any]) -> int:
    """The lap number a split was recorded under."""
    return int(_as_float(row.get("split_index")) or 0)


# --- Step scenes ------------------------------------------------------------


def _step_scene(
    step: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A short step told as one scene: it *is* the unit the athlete ran."""
    kind = _step_kind(step, steps)
    facts: dict[str, Any] = {
        "distance_km": step["distance_km"],
        "duration_s": step["duration_s"],
    }
    for key in ("pace_s_per_km", "avg_hr", "max_hr"):
        if step[key] is not None:
            facts[key] = step[key]

    if kind == "rest":
        drop = _hr_drop(step, steps)
        if drop is not None:
            facts["hr_drop_bpm"] = drop
    elif kind == "rep":
        facts.update(_rep_facts(step, steps))

    return _assemble_scene(
        kind,
        unit="step",
        label_ja=str(step["label_ja"]),
        step_id=str(step["id"]),
        rep_no=step["rep_no"],
        km_from=step["start_km"],
        km_to=step["end_km"],
        t_from_s=step["start_s"],
        t_to_s=step["end_s"],
        split_from=step["split_from"],
        split_to=step["split_to"],
        facts=facts,
    )


def _step_kind(step: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> str:
    """``warmup`` / ``rep`` / ``rest`` / ``main`` / ``cooldown`` for a step."""
    role = step["role"]
    if role == "recovery":
        return "rest"
    if role == "run":
        return "rep" if _has_rep_structure(steps) else "main"
    return str(role)


def _hr_drop(
    step: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]
) -> float | int | None:
    """How far heart rate came down during a rest, from the rep before it."""
    previous = None
    for candidate in steps:
        if candidate["id"] == step["id"]:
            break
        if candidate["role"] == "run":
            previous = candidate
    if previous is None or previous["max_hr"] is None or step["avg_hr"] is None:
        return None
    return _round(float(previous["max_hr"]) - float(step["avg_hr"]))


def _rep_facts(
    step: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Every rep against the first one -- the only comparison a rep needs."""
    first = next((s for s in steps if s["role"] == "run"), None)
    facts: dict[str, Any] = {}
    if first is None:
        return facts
    if step["pace_s_per_km"] is not None and first["pace_s_per_km"] is not None:
        facts["pace_vs_first_s"] = _round(
            float(step["pace_s_per_km"]) - float(first["pace_s_per_km"])
        )
    if step["max_hr"] is not None and first["max_hr"] is not None:
        facts["max_hr_vs_first"] = _round(
            float(step["max_hr"]) - float(first["max_hr"])
        )
    return facts


def _collapse_work_set(
    scenes: list[dict[str, Any]], steps: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Merge the reps and rests of a long rep session into one scene.

    Eight reps would otherwise push the warmup and the cooldown out of the
    five-scene cap, and "8本目まで維持" is the story anyway -- the per-rep
    numbers ride along as facts.
    """
    if not _has_rep_structure(steps):
        return scenes
    work = [scene for scene in scenes if scene["kind"] in {"rep", "rest"}]
    if len(scenes) <= MAX_MOMENTS or len(work) < 2:
        return scenes

    reps = [scene for scene in work if scene["kind"] == "rep"]
    paces = [
        pace
        for scene in reps
        if (pace := _as_float(scene["facts"].get("pace_s_per_km"))) is not None
    ]
    facts: dict[str, Any] = {
        "reps": [_work_entry(scene) for scene in reps],
        "rests": [_work_entry(scene) for scene in work if scene["kind"] == "rest"],
    }
    if len(paces) >= 2:
        facts["first_vs_last_s"] = _round(paces[-1] - paces[0])
        facts["pace_spread_s"] = _round(max(paces) - min(paces))

    merged = _assemble_scene(
        "work_set",
        unit="step",
        label_ja=f"本編（1〜{len(reps)}本目）",
        step_id=str(work[0]["step_id"]),
        rep_no=None,
        km_from=work[0]["km_from"],
        km_to=work[-1]["km_to"],
        t_from_s=work[0]["t_from_s"],
        t_to_s=work[-1]["t_to_s"],
        split_from=work[0]["split_from"],
        split_to=work[-1]["split_to"],
        facts=facts,
    )
    kept = [scene for scene in scenes if scene["kind"] not in {"rep", "rest"}]
    return [*kept, merged]


def _work_entry(scene: Mapping[str, Any]) -> dict[str, Any]:
    """One rep (or rest) as it appears inside a merged ``work_set``."""
    entry: dict[str, Any] = {"label_ja": scene["label_ja"]}
    if scene.get("rep_no") is not None:
        entry["rep_no"] = scene["rep_no"]
    for key in ("distance_km", "duration_s", "pace_s_per_km", "avg_hr", "max_hr"):
        if key in scene["facts"]:
            entry[key] = scene["facts"][key]
    return entry


def _strides_scene(steps: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """One block of strides and their jogs, told as a single scene (#1297).

    Strides are a few seconds of fast running inside an easy run: the story is
    how quick and how relaxed they were, not four ``rep`` scenes and four
    ``rest`` scenes that would push the jog out of the five-scene cap.

    Args:
        steps: The block's consecutive ``stride`` and ``recovery`` steps, in
            run order (see :func:`_strides_blocks`).

    Returns:
        A ``kind='strides'``, ``unit='step'`` scene whose facts are ``reps``,
        ``fastest_pace_s_per_km``, ``median_pace_s_per_km``,
        ``median_cadence_spm``, ``peak_hr`` and ``hr_at_next_start`` -- per
        stride, the average HR of the jog after it, i.e. the heart rate the
        next stride (or the rest of the run) starts from; ``None`` for a stride
        with no recorded jog after it. ``None`` when the block has no stride.
    """
    strides = [step for step in steps if step["role"] == "stride"]
    if not strides:
        return None

    paces = [
        pace
        for step in strides
        if (pace := _as_float(step.get("pace_s_per_km"))) is not None
    ]
    cadences = [
        cadence
        for step in strides
        if (cadence := _weighted_cadence(step.get("rows") or [])) is not None
    ]
    peaks = [
        peak for step in steps if (peak := _as_float(step.get("max_hr"))) is not None
    ]

    facts: dict[str, Any] = {"reps": len(strides)}
    if paces:
        facts["fastest_pace_s_per_km"] = _round(min(paces))
        facts["median_pace_s_per_km"] = _round(median(paces))
    if cadences:
        facts["median_cadence_spm"] = _round(median(cadences))
    if peaks:
        facts["peak_hr"] = _round(max(peaks))
    facts["hr_at_next_start"] = [_jog_hr_after(stride, steps) for stride in strides]

    first, last = steps[0], steps[-1]
    return _assemble_scene(
        "strides",
        unit="step",
        label_ja=f"流し（{len(strides)}本）",
        step_id=str(first["id"]),
        rep_no=None,
        km_from=first["start_km"],
        km_to=last["end_km"],
        t_from_s=first["start_s"],
        t_to_s=last["end_s"],
        split_from=first["split_from"],
        split_to=last["split_to"],
        facts=facts,
    )


def _jog_hr_after(
    stride: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]
) -> float | int | None:
    """Average HR of the jog right after ``stride`` inside its block."""
    ids = [step["id"] for step in steps]
    position = ids.index(stride["id"])
    if position + 1 >= len(steps):
        return None
    following = steps[position + 1]
    if following["role"] != "recovery":
        return None
    hr = _as_float(following.get("avg_hr"))
    return None if hr is None else _round(hr)


def _weighted_cadence(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """Time-weighted cadence over the rows that recorded one."""
    pairs = [
        (cadence, float(row.get("duration_s") or 0.0))
        for row in rows
        if (cadence := _as_float(row.get("cadence"))) is not None
    ]
    if not pairs:
        return None
    weight = sum(duration for _, duration in pairs)
    if weight <= 0:
        return sum(cadence for cadence, _ in pairs) / len(pairs)
    return sum(cadence * duration for cadence, duration in pairs) / weight


# --- Kilometre scenes -------------------------------------------------------


def _km_scenes(
    step: Mapping[str, Any],
    *,
    hr_ceiling: int | None,
    prescription: Mapping[str, Any] | None,
    named: bool,
    breakdown_from_km: float | None = None,
) -> list[dict[str, Any]]:
    """The turning points *inside* one long step, narrated in kilometres."""
    valid = _valid_splits(step["rows"])
    if not valid:
        return []

    prefix = f"{step['label_ja']} " if named else ""
    if step["role"] == "run" and _is_progression(prescription, valid):
        return [_progression_scene(step, valid, prefix)]

    run_median = _run_median_pace(valid)
    first_third_median = _first_third_median_pace(valid)

    candidates = _candidate_scenes(
        valid,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
        breakdown_from_km=breakdown_from_km,
    )
    candidates = _resolve_overlaps(valid, candidates)
    if not any(kind != "start" for kind, _ in candidates):
        return [_steady_scene(step, valid, run_median, prefix)]

    candidates = _cap_per_kind(candidates, valid)
    candidates = _cap_total(candidates, valid)

    corrections = _corrections(valid)
    return [
        _km_scene(
            kind,
            step,
            valid,
            members,
            prefix=prefix,
            hr_ceiling=hr_ceiling,
            run_median=run_median,
            first_third_median=first_third_median,
            corrections=corrections,
        )
        for kind, members in candidates
    ]


def _valid_splits(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Drop GPS fragments and rows without a usable pace, keeping input order."""
    return [dict(row) for row in rows if _is_drawable(row)]


def _run_median_pace(valid: Sequence[Mapping[str, Any]]) -> float:
    """Median pace over the *running* splits (walk laps must not raise the bar)."""
    paces = [_as_float(s.get("pace_s_per_km")) for s in valid]
    running = [p for p in paces if p is not None and p < MAX_RUNNING_PACE_S_PER_KM]
    if not running:
        running = [p for p in paces if p is not None]
    return float(median(running))


def _first_third_median_pace(valid: Sequence[Mapping[str, Any]]) -> float:
    """Median pace of the opening third -- the baseline a fade is measured from."""
    size = _third_size(len(valid))
    paces = [_as_float(s.get("pace_s_per_km")) or 0.0 for s in valid[:size]]
    return float(median(paces))


def _third_size(count: int) -> int:
    """Number of splits in a third of the run (at least one)."""
    return max(1, math.ceil(count / 3))


def _is_progression(
    prescription: Mapping[str, Any] | None, valid: Sequence[Mapping[str, Any]]
) -> bool:
    """Whether this step is the prescribed build-up, per ``derivations``."""
    return detect_progression_session(
        dict(prescription) if prescription is not None else None,
        [
            {
                "avg_heart_rate": _as_float(row.get("avg_hr")),
                "avg_pace_seconds_per_km": _as_float(row.get("pace_s_per_km")),
            }
            for row in valid
        ],
    )


# --- Candidate scenes -------------------------------------------------------


def _candidate_scenes(
    valid: Sequence[Mapping[str, Any]],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
    breakdown_from_km: float | None = None,
) -> list[_Candidate]:
    """Every scene each rule wants, before overlaps and caps are settled."""
    count = len(valid)
    candidates: list[_Candidate] = []

    breakdown = _breakdown_members(valid, breakdown_from_km)
    if breakdown:
        candidates.append(("breakdown", breakdown))

    for members in _merge_runs(
        [i for i in range(count) if _is_ceiling_touch(valid, i, hr_ceiling)]
    ):
        candidates.append(("ceiling_touch", members))

    fade = _fade_members(valid, first_third_median)
    if fade:
        candidates.append(("fade", fade))

    strong_finish = _strong_finish_members(valid, hr_ceiling, run_median)
    if strong_finish:
        candidates.append(("strong_finish", strong_finish))

    walk = [i for i in range(count) if _is_walk_break(valid, i, run_median)]
    if walk:
        candidates.append(("walk_break", walk))

    fast_start = _fast_start_members(valid, run_median)
    if fast_start:
        candidates.append(("fast_start", fast_start))

    surges = [
        i
        for i in range(count)
        if i not in fast_start and _is_surge(valid, i, run_median)
    ]
    for members in _merge_runs(surges):
        candidates.append(("surge", members))

    for members in _merge_runs([i for i in range(count) if _is_climb(valid, i)]):
        candidates.append(("climb", members))

    if not fast_start:
        candidates.append(("start", [0]))

    return candidates


def _breakdown_members(
    valid: Sequence[Mapping[str, Any]], breakdown_from_km: float | None
) -> list[int]:
    """The splits from where the run came apart to the finish (#1340)."""
    if breakdown_from_km is None:
        return []
    return [
        i
        for i, row in enumerate(valid)
        if (_as_float(row.get("start_km")) or 0.0) >= breakdown_from_km - 1e-6
    ]


def _merge_runs(indices: Sequence[int]) -> list[list[int]]:
    """Group indices into scenes, bridging gaps of ``MERGE_GAP_SPLITS`` splits.

    The bridged splits join the scene: a scene occupies its whole
    ``km_from..km_to`` span, so its members and its distance must agree.
    """
    groups: list[list[int]] = []
    for index in indices:
        if groups and index - groups[-1][-1] <= MERGE_GAP_SPLITS + 1:
            groups[-1].extend(range(groups[-1][-1] + 1, index + 1))
        else:
            groups.append([index])
    return groups


def _is_ceiling_touch(
    valid: Sequence[Mapping[str, Any]], i: int, hr_ceiling: int | None
) -> bool:
    """Sustained contact with the ceiling, not a momentary peak (#1261).

    Either the kilometre averages at or above the ceiling, or its peak clears
    the ceiling by ``CEILING_PEAK_MARGIN_BPM`` *while the average is already
    there*. A 155 bpm spike inside a kilometre averaging 131 is HR noise, not
    effort spent against the ceiling.
    """
    if hr_ceiling is None:
        return False
    avg_hr = _as_float(valid[i].get("avg_hr"))
    if avg_hr is not None and avg_hr >= hr_ceiling:
        return True
    max_hr = _as_float(valid[i].get("max_hr"))
    if max_hr is None or avg_hr is None:
        return False
    return (
        max_hr >= hr_ceiling + CEILING_PEAK_MARGIN_BPM
        and avg_hr >= hr_ceiling - CEILING_NEAR_BPM
    )


def _corrections(valid: Sequence[Mapping[str, Any]]) -> dict[int, float]:
    """Splits where the athlete eased off, mapped to the pace they gave back.

    A correction only means something next to a ceiling touch, where it is
    recorded as a fact of that scene (``corrected_at_km``); on its own it is
    just a slower kilometre. It needs a following split: the proof that easing
    off worked is the *next* kilometre's average HR no longer climbing.
    """
    found: dict[int, float] = {}
    for i in range(1, len(valid) - 1):
        pace = _as_float(valid[i].get("pace_s_per_km"))
        prev_pace = _as_float(valid[i - 1].get("pace_s_per_km"))
        if pace is None or prev_pace is None:
            continue
        drop = pace - prev_pace
        if drop < CORRECTION_S_PER_KM:
            continue
        avg_hr = _as_float(valid[i].get("avg_hr"))
        next_hr = _as_float(valid[i + 1].get("avg_hr"))
        if avg_hr is None or next_hr is None or next_hr > avg_hr:
            continue
        found[i] = drop
    return found


def _fade_members(
    valid: Sequence[Mapping[str, Any]], first_third_median: float
) -> list[int]:
    """The closing stretch that keeps losing pace all the way to the finish.

    A fade has to *end the run*: the 7/31 recovery run's one slow kilometre was
    followed by its fastest, which is a dip, not a fade (#1261).
    """
    count = len(valid)
    qualifying = [i for i in range(count) if _is_fade(valid, i, first_third_median)]
    final = next(
        (members for members in _merge_runs(qualifying) if members[-1] == count - 1),
        None,
    )
    if final is None:
        return []
    minimum = FADE_MIN_SPLITS if count >= FADE_SHORT_RUN_SPLITS else 1
    return final if len(final) >= minimum else []


def _is_fade(
    valid: Sequence[Mapping[str, Any]], i: int, first_third_median: float
) -> bool:
    """Losing pace in the closing third while heart rate refuses to come down.

    HR *falling* means the athlete chose to ease off (or is walking); that is a
    different story, told by ``walk_break`` or by a touch's ``corrected_at_km``.
    """
    size = _third_size(len(valid))
    if i == 0 or i < len(valid) - size:
        return False
    pace = _as_float(valid[i].get("pace_s_per_km"))
    if pace is None or pace - first_third_median < FADE_S_PER_KM:
        return False
    avg_hr = _as_float(valid[i].get("avg_hr"))
    prev_hr = _as_float(valid[i - 1].get("avg_hr"))
    if avg_hr is None or prev_hr is None:
        return False
    return avg_hr >= prev_hr


def _is_walk_break(
    valid: Sequence[Mapping[str, Any]], i: int, run_median: float
) -> bool:
    """Walking cadence *and* a pace cost against the run median."""
    cadence = _as_float(valid[i].get("cadence"))
    if cadence is None or cadence >= WALK_CADENCE_SPM:
        return False
    pace = _as_float(valid[i].get("pace_s_per_km"))
    return pace is not None and pace - run_median >= WALK_PACE_S_PER_KM


def _fast_start_members(
    valid: Sequence[Mapping[str, Any]], run_median: float
) -> list[int]:
    """The opening 1-2 kilometres, if they were run clearly faster than the rest."""
    members: list[int] = []
    for i in range(min(FAST_START_MAX_SPLITS, len(valid))):
        pace = _as_float(valid[i].get("pace_s_per_km"))
        if pace is None or run_median - pace < FAST_START_S_PER_KM:
            break
        members.append(i)
    return members


def _is_surge(valid: Sequence[Mapping[str, Any]], i: int, run_median: float) -> bool:
    """Faster than the run median by a clear margin."""
    pace = _as_float(valid[i].get("pace_s_per_km"))
    return pace is not None and run_median - pace >= SURGE_S_PER_KM


def _is_climb(valid: Sequence[Mapping[str, Any]], i: int) -> bool:
    """Enough gain inside the kilometre that the hill is its story."""
    gain = _as_float(valid[i].get("elevation_gain_m"))
    return gain is not None and gain >= CLIMB_M_PER_KM


def _strong_finish_members(
    valid: Sequence[Mapping[str, Any]], hr_ceiling: int | None, run_median: float
) -> list[int]:
    """Closing splits that are all faster than the median at a contained HR."""
    total_km = sum(_as_float(s.get("distance_km")) or 0.0 for s in valid)
    window = 1 if total_km < STRONG_FINISH_SHORT_RUN_KM else STRONG_FINISH_SPLITS
    if len(valid) < window:
        return []

    hr_limit: float | None
    if hr_ceiling is not None:
        hr_limit = float(hr_ceiling)
    else:
        hr_values = [h for h in (_as_float(s.get("avg_hr")) for s in valid) if h]
        hr_limit = (
            _percentile(hr_values, STRONG_FINISH_HR_PERCENTILE) if hr_values else None
        )

    members = list(range(len(valid) - window, len(valid)))
    for i in members:
        pace = _as_float(valid[i].get("pace_s_per_km"))
        if pace is None or pace >= run_median:
            return []
        if hr_limit is None:
            continue
        avg_hr = _as_float(valid[i].get("avg_hr"))
        if avg_hr is not None and avg_hr > hr_limit:
            return []
    return members


# --- Overlaps and caps ------------------------------------------------------


def _resolve_overlaps(
    valid: Sequence[Mapping[str, Any]], candidates: Sequence[_Candidate]
) -> list[_Candidate]:
    """Give every split to the highest-priority scene claiming it.

    One event used to produce two adjacent bands -- a ceiling touch and the
    correction answering it -- which reads as two things happening. Now the
    loser keeps only the splits nobody above it wants, and a scene trimmed
    to nothing is dropped.
    """
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            _priority_rank(candidate[0]),
            -len(candidate[1]),
            candidate[1][0],
        ),
    )

    taken: set[int] = set()
    kept: list[_Candidate] = []
    for kind, members in ordered:
        remaining = [i for i in members if i not in taken]
        if kind != "walk_break":
            remaining = _longest_block(remaining)
        if not remaining:
            continue
        taken.update(remaining)
        kept.append((kind, remaining))
    return kept


def _longest_block(members: Sequence[int]) -> list[int]:
    """The longest run of consecutive indices (earliest on a tie).

    Trimming can punch a hole in a scene, and a scene is one continuous stretch
    of the run, so only the surviving stretch is kept.
    """
    best: list[int] = []
    current: list[int] = []
    for index in members:
        current = current + [index] if current and index == current[-1] + 1 else [index]
        if len(current) > len(best):
            best = current
    return list(best)


def _cap_per_kind(
    candidates: Sequence[_Candidate], valid: Sequence[Mapping[str, Any]]
) -> list[_Candidate]:
    """At most ``MAX_PER_KIND`` scenes of one kind: the longest, then earliest.

    Four ceiling touches on a 25 km run filled every slot and pushed the closing
    3 km -- the story of that day -- out of the report (#1261).
    """
    counts: dict[str, int] = {}
    kept: list[_Candidate] = []
    for kind, members in sorted(candidates, key=lambda c: _kind_length_key(c, valid)):
        if counts.get(kind, 0) >= MAX_PER_KIND:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        kept.append((kind, members))
    return kept


def _cap_total(
    candidates: Sequence[_Candidate], valid: Sequence[Mapping[str, Any]]
) -> list[_Candidate]:
    """Keep the ``MAX_MOMENTS`` most newsworthy scenes of one step."""
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            _priority_rank(candidate[0]),
            -len(candidate[1]),
            candidate[1][0],
        ),
    )
    return ranked[:MAX_MOMENTS]


def _cap_scenes(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep the ``MAX_MOMENTS`` most newsworthy scenes of the whole run."""
    ranked = sorted(
        scenes,
        key=lambda scene: (
            _priority_rank(str(scene["kind"])),
            -(int(scene["split_to"]) - int(scene["split_from"]) + 1),
            int(scene["split_from"]),
        ),
    )
    kept = [dict(scene) for scene in ranked[:MAX_MOMENTS]]
    kept.sort(key=lambda scene: (scene["split_from"], scene["split_to"]))
    return kept


def _kind_length_key(
    candidate: _Candidate, valid: Sequence[Mapping[str, Any]]
) -> tuple[str, int, int]:
    """Sort key grouping scenes by kind, longest first, then earliest."""
    kind, members = candidate
    return (kind, -len(members), members[0])


def _priority_rank(kind: str) -> int:
    """Tier in :data:`_PRIORITY`; unknown kinds sort last."""
    return _RANK.get(kind, len(_PRIORITY))


# --- Scene assembly ---------------------------------------------------------


def _assemble_scene(
    kind: str,
    *,
    unit: str,
    label_ja: str,
    step_id: str,
    rep_no: int | None,
    km_from: float,
    km_to: float,
    t_from_s: float,
    t_to_s: float,
    split_from: int,
    split_to: int,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """One scene dict (``id`` is assigned later, once they are ordered)."""
    return {
        "id": "",
        "kind": kind,
        "unit": unit,
        "label_ja": label_ja,
        "step_id": step_id,
        "rep_no": rep_no,
        "km_from": km_from,
        "km_to": km_to,
        "t_from_s": t_from_s,
        "t_to_s": t_to_s,
        "split_from": split_from,
        "split_to": split_to,
        "facts": facts,
    }


def _km_scene(
    kind: str,
    step: Mapping[str, Any],
    valid: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    *,
    prefix: str,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
    corrections: Mapping[int, float],
) -> dict[str, Any]:
    """One scene inside a long step, positioned and named in kilometres."""
    rows = [valid[i] for i in members]
    facts = _facts(
        kind,
        valid,
        members,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
        corrections=corrections,
    )
    label = (
        _walk_label(facts["km_list"])
        if kind == "walk_break"
        else _span_label(rows[0]["start_km"], rows[-1]["end_km"])
    )
    return _assemble_scene(
        kind,
        unit="km",
        label_ja=f"{prefix}{label}",
        step_id=str(step["id"]),
        rep_no=None,
        km_from=rows[0]["start_km"],
        km_to=rows[-1]["end_km"],
        t_from_s=rows[0]["start_s"],
        t_to_s=rows[-1]["end_s"],
        split_from=_split_index(rows[0]),
        split_to=_split_index(rows[-1]),
        facts=facts,
    )


def _facts(
    kind: str,
    valid: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
    corrections: Mapping[int, float],
) -> dict[str, Any]:
    """The numbers the narration is allowed to quote for this scene."""
    rows = [valid[i] for i in members]
    paces = [
        p for p in (_as_float(r.get("pace_s_per_km")) for r in rows) if p is not None
    ]
    hrs = [h for h in (_as_float(r.get("avg_hr")) for r in rows) if h is not None]
    max_hrs = [h for h in (_as_float(r.get("max_hr")) for r in rows) if h is not None]

    facts: dict[str, Any] = {}
    if paces:
        facts["pace_s_per_km"] = _round(median(paces))
    if hrs:
        facts["avg_hr"] = _round(median(hrs))

    if kind == "ceiling_touch":
        if max_hrs:
            facts["max_hr"] = _round(max(max_hrs))
        if hr_ceiling is not None:
            facts["hr_ceiling"] = int(hr_ceiling)
        _add_correction_facts(facts, valid, members, corrections)
    elif kind == "walk_break":
        facts["km_list"] = [row["start_km"] for row in rows]
        facts["split_list"] = [_split_index(row) for row in rows]
        cadences = [
            c for c in (_as_float(r.get("cadence")) for r in rows) if c is not None
        ]
        if cadences:
            facts["cadence"] = _round(min(cadences))
        if paces:
            facts["pace_s_per_km"] = _round(max(paces))
    elif kind == "climb":
        gains = [
            g
            for g in (_as_float(r.get("elevation_gain_m")) for r in rows)
            if g is not None
        ]
        if gains:
            facts["elevation_gain_m"] = _round(sum(gains))
    elif kind in {"fade", "breakdown"}:
        if paces:
            facts["pace_delta_s_per_km"] = _round(median(paces) - first_third_median)
            facts["first_third_pace_s_per_km"] = _round(first_third_median)
    elif kind in {"surge", "fast_start", "strong_finish"}:
        if paces:
            reference = min(paces) if kind == "surge" else median(paces)
            facts["pace_s_per_km"] = _round(reference)
            facts["pace_delta_s_per_km"] = _round(run_median - reference)
            facts["median_pace_s_per_km"] = _round(run_median)
        if kind == "strong_finish" and hr_ceiling is not None:
            facts["hr_ceiling"] = int(hr_ceiling)
    return facts


def _add_correction_facts(
    facts: dict[str, Any],
    valid: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    corrections: Mapping[int, float],
) -> None:
    """Record the easing-off that answered this touch, if there was one.

    The correction may sit inside the scene or on the split immediately before
    or after it -- backing off at the edge of a touch is the same event, and it
    used to be drawn as a scene of its own (#1261).
    """
    window = range(members[0] - 1, members[-1] + 2)
    index = next((i for i in window if i in corrections), None)
    if index is None:
        return
    facts["corrected_at_km"] = valid[index]["start_km"]
    facts["corrected_at_split"] = _split_index(valid[index])
    facts["pace_drop_s_per_km"] = _round(corrections[index])


def _steady_scene(
    step: Mapping[str, Any],
    valid: Sequence[Mapping[str, Any]],
    run_median: float,
    prefix: str,
) -> dict[str, Any]:
    """The whole step as one scene: nothing turned, and that is the story."""
    hrs = [h for h in (_as_float(s.get("avg_hr")) for s in valid) if h is not None]
    facts: dict[str, Any] = {"pace_s_per_km": _round(run_median)}
    if hrs:
        facts["avg_hr"] = _round(median(hrs))
        facts["hr_range"] = [_round(min(hrs)), _round(max(hrs))]
    return _assemble_scene(
        "steady",
        unit="km",
        label_ja=f"{prefix}{_span_label(valid[0]['start_km'], valid[-1]['end_km'])}",
        step_id=str(step["id"]),
        rep_no=None,
        km_from=valid[0]["start_km"],
        km_to=valid[-1]["end_km"],
        t_from_s=valid[0]["start_s"],
        t_to_s=valid[-1]["end_s"],
        split_from=_split_index(valid[0]),
        split_to=_split_index(valid[-1]),
        facts=facts,
    )


def _progression_scene(
    step: Mapping[str, Any], valid: Sequence[Mapping[str, Any]], prefix: str
) -> dict[str, Any]:
    """A prescribed build-up: the ramp itself is the scene, km by km."""
    facts: dict[str, Any] = {
        "per_km": [
            {
                "km": row["start_km"],
                "pace_s_per_km": _round(_as_float(row.get("pace_s_per_km")) or 0.0),
                "avg_hr": _round(_as_float(row.get("avg_hr")) or 0.0),
            }
            for row in valid
        ]
    }
    first_pace = _as_float(valid[0].get("pace_s_per_km"))
    last_pace = _as_float(valid[-1].get("pace_s_per_km"))
    if first_pace is not None and last_pace is not None:
        facts["pace_gain_s_per_km"] = _round(first_pace - last_pace)
    first_hr = _as_float(valid[0].get("avg_hr"))
    last_hr = _as_float(valid[-1].get("avg_hr"))
    if first_hr is not None and last_hr is not None:
        facts["hr_gain_bpm"] = _round(last_hr - first_hr)
    return _assemble_scene(
        "progression",
        unit="km",
        label_ja=f"{prefix}{_span_label(valid[0]['start_km'], valid[-1]['end_km'])}",
        step_id=str(step["id"]),
        rep_no=None,
        km_from=valid[0]["start_km"],
        km_to=valid[-1]["end_km"],
        t_from_s=valid[0]["start_s"],
        t_to_s=valid[-1]["end_s"],
        split_from=_split_index(valid[0]),
        split_to=_split_index(valid[-1]),
        facts=facts,
    )


def _number(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign ``m1..mN`` in run order."""
    for n, scene in enumerate(scenes, start=1):
        scene["id"] = f"m{n}"
    return scenes


# --- Labels -----------------------------------------------------------------


def _span_label(km_from: float, km_to: float) -> str:
    """``"3–5 km"`` / ``"2.6–4.6 km"`` -- the stretch of road a scene covers."""
    return f"{_km_text(km_from)}–{_km_text(km_to)} km"


def _walk_label(km_list: Sequence[float]) -> str:
    """``"13・19・21 km 付近"`` -- where the athlete stopped running."""
    return "・".join(_km_text(km) for km in km_list) + " km 付近"


def _km_text(value: float) -> str:
    """One decimal, but only when the distance actually needs it."""
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


# --- Recurrence helpers -----------------------------------------------------


def _is_step_scene(moment: Mapping[str, Any]) -> bool:
    """Whether a scene is named after a step rather than a stretch of road."""
    return str(moment.get("unit") or "km") == "step"


def _run_has_moment_near(run: Mapping[str, Any], moment: Mapping[str, Any]) -> bool:
    """Whether a previous run has this scene at (about) the same point.

    A kilometre scene is "the same place" within ``RECURRENCE_KM_TOLERANCE``; a
    step scene is the same rep of the session, because "the 3rd rep is where it
    goes" is the pattern a rep session repeats -- not a distance.
    """
    kind = str(moment.get("kind"))
    if kind in _NON_RECURRING_KINDS:
        return False
    km = _as_float(moment.get("km_from"))
    for other in run.get("moments") or []:
        if str(other.get("kind")) != kind:
            continue
        if _is_step_scene(moment):
            if other.get("rep_no") == moment.get("rep_no"):
                return True
            continue
        other_km = _as_float(other.get("km_from"))
        if km is None or other_km is None:
            continue
        if abs(other_km - km) <= RECURRENCE_KM_TOLERANCE:
            return True
    return False


# --- Small helpers ----------------------------------------------------------


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Linear-interpolated percentile (no numpy needed for a handful of values)."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile / 100.0
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def _as_float(value: Any) -> float | None:
    """Float or ``None`` -- readers hand back Decimals, numpy scalars and NULLs."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _round(value: float) -> float | int:
    """One decimal, but keep whole numbers integral so JSON stays readable."""
    rounded = round(float(value), 1)
    return int(rounded) if rounded == int(rounded) else rounded


def _round1(value: float) -> float | int:
    """Seconds at the resolution the device records them."""
    return _round(value)


def _round3(value: float) -> float | int:
    """Distances to the metre -- the resolution positions are accumulated at."""
    rounded = round(float(value), 3)
    return int(rounded) if rounded == int(rounded) else rounded
