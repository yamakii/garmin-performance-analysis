"""Deterministic *scene* detection for a single run (pure, no I/O) -- #1249, #1261.

The split section used to narrate every kilometre ("全スプリット例外なく"), which
is a numeric readout the table already shows. The redesign keeps prose only for
**how the run unfolded**: 2-5 turning points. This module produces those turning
points *deterministically* from the split rows, so the LLM's job shrinks to
selecting and explaining them -- it cannot invent a scene, because a merge guard
checks the ``moment_id``s it cites against :func:`detect_moments` output.

Two functions, both pure and JSON-serialisable:

- :func:`detect_moments` -- one run's split rows -> at most ``MAX_MOMENTS``
  scenes, ordered by ``km_from``.
- :func:`detect_recurrence` -- today's scenes plus the previous same-family runs
  -> the kinds that keep happening at the same place in the run.

Design notes that are easy to get wrong when editing. Every one of them is a
correction the first cut needed once it met real activities (#1261):

* **A momentary peak is not a ceiling touch.** Every kilometre has an HR spike;
  the 9/17 run peaked at 155 bpm inside a kilometre averaging 131 against a 150
  ceiling. Contact has to be *sustained* (:func:`_is_ceiling_touch`), or the
  scene list fills with spikes and :func:`detect_recurrence` reports a habit
  that never happened.
* **Scenes are built per kind, then de-conflicted.** One kilometre can satisfy
  several rules at once (a ceiling touch on a climb). Each kind gets its own
  qualifying splits -- same-kind stretches separated by at most
  ``MERGE_GAP_SPLITS`` merge into one scene -- and afterwards
  :func:`_resolve_overlaps` hands every kilometre to the highest-priority scene
  claiming it, trimming the losers. One event never draws two bands.
* **The end of the run must survive the cap.** A 25 km run that spends its
  middle on the ceiling would otherwise fill all five slots there and drop the
  story of the day (the closing 3 km). ``MAX_PER_KIND`` bounds a single kind
  before the global ``MAX_MOMENTS`` cut.
* **Fragments are dropped before anything is measured.** Manual lap presses
  leave 5-11 m laps whose pace is a measurement artifact (as fast as 4:04/km),
  which would otherwise fake a surge or a ceiling touch. The threshold is
  ``MIN_SPLIT_KM`` from ``form_baseline.split_filter`` so this module and the
  form baseline cannot drift apart.
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

from garmin_mcp.form_baseline.split_filter import (
    MAX_RUNNING_PACE_S_PER_KM,
    MIN_SPLIT_KM,
)

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
# contested kilometre and which scenes survive the ``MAX_MOMENTS`` cap.
_PRIORITY: tuple[tuple[str, ...], ...] = (
    ("ceiling_touch",),
    ("fade", "strong_finish"),
    ("walk_break",),
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


def detect_moments(
    splits: Sequence[Mapping[str, Any]], *, hr_ceiling: int | None
) -> list[dict[str, Any]]:
    """Detect the turning points of one run.

    Args:
        splits: The run's split rows, in order. Each row is read for
            ``split_index``, ``distance_km``, ``pace_s_per_km``, ``avg_hr``,
            ``max_hr``, ``cadence`` and ``elevation_gain_m``; missing or ``None``
            fields simply disable the rules that need them.
        hr_ceiling: The prescription's heart-rate ceiling, or ``None`` when the
            run was not prescribed one. Without it no ``ceiling_touch`` scene
            can exist.

    Returns:
        ``[{"id": "m1", "kind": ..., "km_from": int, "km_to": int,
        "facts": {...}}]`` ordered by ``km_from``, ids renumbered ``m1..mN``
        with ``N <= MAX_MOMENTS``. Scenes never share a kilometre. ``kind`` is
        one of ``start``, ``fast_start``, ``surge``, ``ceiling_touch``,
        ``walk_break``, ``climb``, ``fade``, ``strong_finish``, ``steady``.
        JSON-serialisable throughout. An uneventful run returns a single
        ``steady`` scene; no valid split returns ``[]``.
    """
    valid = _valid_splits(splits)
    if not valid:
        return []

    run_median = _run_median_pace(valid)
    first_third_median = _first_third_median_pace(valid)

    candidates = _candidate_scenes(
        valid,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
    )
    candidates = _resolve_overlaps(valid, candidates)
    if not any(kind != "start" for kind, _ in candidates):
        return _number([_steady_scene(valid, run_median)])

    candidates = _cap_per_kind(candidates, valid)
    candidates = _cap_total(candidates, valid)

    corrections = _corrections(valid)
    scenes = [
        _scene(
            kind,
            valid,
            members,
            hr_ceiling=hr_ceiling,
            run_median=run_median,
            first_third_median=first_third_median,
            corrections=corrections,
        )
        for kind, members in candidates
    ]
    scenes.sort(key=lambda scene: (scene["km_from"], scene["km_to"]))
    return _number(scenes)


def detect_recurrence(
    today: Sequence[Mapping[str, Any]],
    previous_runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Find today's scenes that keep recurring at the same point of the run.

    A scene becomes a coaching observation only once it is a habit: "the HR
    ceiling gets touched around km 4 again" is worth saying, a single touch is
    not.

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
    seen: set[tuple[str, int]] = set()

    for moment in today:
        kind = str(moment.get("kind") or "")
        if not kind or kind in {"start", "steady"}:
            continue
        km = int(_as_float(moment.get("km_from")) or 0)
        if (kind, km) in seen:
            continue
        seen.add((kind, km))

        dates = [
            str(run.get("activity_date"))
            for run in lookback
            if _run_has_moment_near(run, kind, km)
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


def _valid_splits(splits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Drop GPS fragments and rows without a usable pace, keeping input order."""
    valid: list[dict[str, Any]] = []
    for split in splits:
        distance = _as_float(split.get("distance_km"))
        pace = _as_float(split.get("pace_s_per_km"))
        if distance is None or distance < MIN_SPLIT_KM:
            continue
        if pace is None or pace <= 0:
            continue
        valid.append(dict(split))
    return valid


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


# --- Candidate scenes -------------------------------------------------------


def _candidate_scenes(
    valid: Sequence[Mapping[str, Any]],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
) -> list[_Candidate]:
    """Every scene each rule wants, before overlaps and caps are settled."""
    count = len(valid)
    candidates: list[_Candidate] = []

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


def _merge_runs(indices: Sequence[int]) -> list[list[int]]:
    """Group indices into scenes, bridging gaps of ``MERGE_GAP_SPLITS`` splits.

    The bridged splits join the scene: a scene occupies its whole
    ``km_from..km_to`` span, so its members and its kilometres must agree.
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
    """Give every kilometre to the highest-priority scene claiming it.

    One event used to produce two adjacent bands -- a ceiling touch and the
    correction answering it -- which reads as two things happening. Now the
    loser keeps only the kilometres nobody above it wants, and a scene trimmed
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
        remaining = [i for i in members if _km(valid[i]) not in taken]
        if kind != "walk_break":
            remaining = _longest_block(remaining)
        if not remaining:
            continue
        taken.update(_km(valid[i]) for i in remaining)
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
    for kind, members in sorted(
        candidates, key=lambda c: _kind_length_km_key(c, valid)
    ):
        if counts.get(kind, 0) >= MAX_PER_KIND:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        kept.append((kind, members))
    return kept


def _cap_total(
    candidates: Sequence[_Candidate], valid: Sequence[Mapping[str, Any]]
) -> list[_Candidate]:
    """Keep the ``MAX_MOMENTS`` most newsworthy scenes."""
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            _priority_rank(candidate[0]),
            -len(candidate[1]),
            _km(valid[candidate[1][0]]),
        ),
    )
    return ranked[:MAX_MOMENTS]


def _kind_length_km_key(
    candidate: _Candidate, valid: Sequence[Mapping[str, Any]]
) -> tuple[str, int, int]:
    """Sort key grouping scenes by kind, longest first, then earliest."""
    kind, members = candidate
    return (kind, -len(members), _km(valid[members[0]]))


def _priority_rank(kind: str) -> int:
    """Tier in :data:`_PRIORITY`; unknown kinds sort last."""
    return _RANK.get(kind, len(_PRIORITY))


# --- Scene assembly ---------------------------------------------------------


def _scene(
    kind: str,
    valid: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
    corrections: Mapping[int, float],
) -> dict[str, Any]:
    """Build one scene dict (``id`` is assigned later, once they are ordered)."""
    kms = [_km(valid[i]) for i in members]
    facts = _facts(
        kind,
        valid,
        members,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
        corrections=corrections,
    )
    return {
        "id": "",
        "kind": kind,
        "km_from": min(kms),
        "km_to": max(kms),
        "facts": facts,
    }


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
        facts["km_list"] = [_km(row) for row in rows]
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
    elif kind == "fade":
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
    facts["corrected_at_km"] = _km(valid[index])
    facts["pace_drop_s_per_km"] = _round(corrections[index])


def _steady_scene(
    valid: Sequence[Mapping[str, Any]], run_median: float
) -> dict[str, Any]:
    """The whole run as one scene: nothing turned, and that is the story."""
    hrs = [h for h in (_as_float(s.get("avg_hr")) for s in valid) if h is not None]
    facts: dict[str, Any] = {"pace_s_per_km": _round(run_median)}
    if hrs:
        facts["avg_hr"] = _round(median(hrs))
        facts["hr_range"] = [_round(min(hrs)), _round(max(hrs))]
    return {
        "id": "",
        "kind": "steady",
        "km_from": _km(valid[0]),
        "km_to": _km(valid[-1]),
        "facts": facts,
    }


def _number(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign ``m1..mN`` in run order."""
    for n, scene in enumerate(scenes, start=1):
        scene["id"] = f"m{n}"
    return scenes


# --- Recurrence helpers -----------------------------------------------------


def _run_has_moment_near(run: Mapping[str, Any], kind: str, km: int) -> bool:
    """Whether a previous run has this kind of scene at (about) the same km."""
    for moment in run.get("moments") or []:
        if str(moment.get("kind")) != kind:
            continue
        other_km = _as_float(moment.get("km_from"))
        if other_km is None:
            continue
        if abs(other_km - km) <= RECURRENCE_KM_TOLERANCE:
            return True
    return False


# --- Small helpers ----------------------------------------------------------


def _km(split: Mapping[str, Any]) -> int:
    """The kilometre marker a split is reported under."""
    return int(_as_float(split.get("split_index")) or 0)


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
