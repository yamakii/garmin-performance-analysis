"""Deterministic *scene* detection for a single run (pure, no I/O) -- #1249.

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

Design notes that are easy to get wrong when editing:

* **One kind per split.** A kilometre can satisfy several rules at once (a
  ceiling touch on a climb, a self-correction inside a fade). Each split is
  assigned the single highest-priority kind from :data:`_PRIORITY` so scenes
  never overlap; the same order then decides which scenes survive the
  ``MAX_MOMENTS`` cap.
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

# A split counts as a surge when it beats the run median by this margin *and*
# is faster than the split before it (8 s/km is well outside GPS pace noise).
SURGE_S_PER_KM = 8.0

# A self-correction is a visible easing-off: the athlete gives back at least
# this much pace right at (or right after) a ceiling touch.
CORRECTION_S_PER_KM = 10.0

# Below this cadence the athlete is walking, not running (running laps sit at
# ~175 spm, walk laps at ~65-115 spm; 170 leaves room for a tired shuffle).
WALK_CADENCE_SPM = 170.0

# A walk break must also cost pace against the run median -- a low-cadence but
# on-pace split is a stride-length change, not a break.
WALK_PACE_S_PER_KM = 15.0

# Metres of gain within one kilometre that make the climb the story of that km.
CLIMB_M_PER_KM = 15.0

# Last-third pace loss (against the first-third median) that counts as a fade,
# but only while heart rate holds -- see :func:`_is_fade`.
FADE_S_PER_KM = 15.0

# A strong finish looks at the last ``STRONG_FINISH_SPLITS`` splits, or just the
# final one on runs shorter than ``STRONG_FINISH_SHORT_RUN_KM`` (where three
# kilometres would be half the run).
STRONG_FINISH_SPLITS = 3
STRONG_FINISH_SHORT_RUN_KM = 8.0
# Without a prescribed ceiling, "contained HR" means not above the run's own
# heart-rate distribution at this percentile.
STRONG_FINISH_HR_PERCENTILE = 90.0

# At most this many scenes reach the narration; the rest are dropped by
# :data:`_PRIORITY`.
MAX_MOMENTS = 5

# --- Recurrence -------------------------------------------------------------

# How many previous same-intensity-family runs to look back over.
RECURRENCE_LOOKBACK = 4
# Two scenes are "the same place in the run" within this many kilometres.
RECURRENCE_KM_TOLERANCE = 1.0
# A pattern is only worth mentioning once it has happened on this many runs.
RECURRENCE_MIN_COUNT = 2

# Most-to-least newsworthy. Decides both the kind of a split that matches
# several rules and which scenes survive the ``MAX_MOMENTS`` cap.
_PRIORITY: tuple[str, ...] = (
    "ceiling_touch",
    "self_correction",
    "fade",
    "walk_break",
    "strong_finish",
    "surge",
    "climb",
    "start",
)


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
            run was not prescribed one. Without it no ``ceiling_touch`` /
            ``self_correction`` scene can exist.

    Returns:
        ``[{"id": "m1", "kind": ..., "km_from": int, "km_to": int,
        "facts": {...}}]`` ordered by ``km_from``, ids renumbered ``m1..mN``
        with ``N <= MAX_MOMENTS``. JSON-serialisable throughout. An uneventful
        run returns a single ``steady`` scene; no valid split returns ``[]``.
    """
    valid = _valid_splits(splits)
    if not valid:
        return []

    run_median = _run_median_pace(valid)
    first_third_median = _first_third_median_pace(valid)
    kinds = _assign_kinds(
        valid,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
    )

    scenes = _build_scenes(
        valid,
        kinds,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
    )
    if not any(scene["kind"] != "start" for scene in scenes):
        scenes = [_steady_scene(valid, run_median)]

    return _cap_and_number(scenes)


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


# --- Per-split classification ----------------------------------------------


def _assign_kinds(
    valid: Sequence[Mapping[str, Any]],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
) -> list[str | None]:
    """Give every valid split its single highest-priority kind (or ``None``)."""
    ceiling_touches = [
        _is_ceiling_touch(valid, i, hr_ceiling) for i in range(len(valid))
    ]
    strong_finish = _strong_finish_indices(valid, hr_ceiling, run_median)

    kinds: list[str | None] = []
    for i in range(len(valid)):
        candidates: set[str] = set()
        if i == 0:
            candidates.add("start")
        if ceiling_touches[i]:
            candidates.add("ceiling_touch")
        if _is_self_correction(valid, i, ceiling_touches):
            candidates.add("self_correction")
        if _is_fade(valid, i, first_third_median):
            candidates.add("fade")
        if _is_walk_break(valid, i, run_median):
            candidates.add("walk_break")
        if i in strong_finish:
            candidates.add("strong_finish")
        if _is_surge(valid, i, run_median):
            candidates.add("surge")
        if _is_climb(valid, i):
            candidates.add("climb")
        kinds.append(next((k for k in _PRIORITY if k in candidates), None))
    return kinds


def _is_ceiling_touch(
    valid: Sequence[Mapping[str, Any]], i: int, hr_ceiling: int | None
) -> bool:
    """Crossing the ceiling with peak HR, or sitting on it on average."""
    if hr_ceiling is None:
        return False
    avg_hr = _as_float(valid[i].get("avg_hr"))
    if avg_hr is not None and avg_hr >= hr_ceiling:
        return True
    max_hr = _as_float(valid[i].get("max_hr"))
    if max_hr is None or max_hr < hr_ceiling:
        return False
    if i == 0:
        # No previous split: the crossing happens here by definition.
        return True
    prev_max = _as_float(valid[i - 1].get("max_hr"))
    return prev_max is None or prev_max < hr_ceiling


def _is_self_correction(
    valid: Sequence[Mapping[str, Any]], i: int, ceiling_touches: Sequence[bool]
) -> bool:
    """Backing off at (or right after) a ceiling touch, with HR answering.

    Requires a following split: the proof that the correction worked is the
    *next* kilometre's average HR no longer climbing.
    """
    if i == 0 or i + 1 >= len(valid):
        return False
    if not (ceiling_touches[i] or ceiling_touches[i - 1]):
        return False
    pace = _as_float(valid[i].get("pace_s_per_km"))
    prev_pace = _as_float(valid[i - 1].get("pace_s_per_km"))
    if pace is None or prev_pace is None or pace - prev_pace < CORRECTION_S_PER_KM:
        return False
    avg_hr = _as_float(valid[i].get("avg_hr"))
    next_hr = _as_float(valid[i + 1].get("avg_hr"))
    if avg_hr is None or next_hr is None:
        return False
    return next_hr <= avg_hr


def _is_fade(
    valid: Sequence[Mapping[str, Any]], i: int, first_third_median: float
) -> bool:
    """Losing pace in the closing third while heart rate refuses to come down.

    HR *falling* means the athlete chose to ease off (or is walking); that is a
    different story, told by ``self_correction`` / ``walk_break``.
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


def _is_surge(valid: Sequence[Mapping[str, Any]], i: int, run_median: float) -> bool:
    """Faster than the run median by a clear margin, and still accelerating."""
    if i == 0:
        return False
    pace = _as_float(valid[i].get("pace_s_per_km"))
    prev_pace = _as_float(valid[i - 1].get("pace_s_per_km"))
    if pace is None or prev_pace is None:
        return False
    return run_median - pace >= SURGE_S_PER_KM and pace < prev_pace


def _is_climb(valid: Sequence[Mapping[str, Any]], i: int) -> bool:
    """Enough gain inside the kilometre that the hill is its story."""
    gain = _as_float(valid[i].get("elevation_gain_m"))
    return gain is not None and gain >= CLIMB_M_PER_KM


def _strong_finish_indices(
    valid: Sequence[Mapping[str, Any]], hr_ceiling: int | None, run_median: float
) -> set[int]:
    """Closing splits that are all faster than the median at a contained HR."""
    total_km = sum(_as_float(s.get("distance_km")) or 0.0 for s in valid)
    window = 1 if total_km < STRONG_FINISH_SHORT_RUN_KM else STRONG_FINISH_SPLITS
    if len(valid) < window:
        return set()

    hr_limit: float | None
    if hr_ceiling is not None:
        hr_limit = float(hr_ceiling)
    else:
        hr_values = [h for h in (_as_float(s.get("avg_hr")) for s in valid) if h]
        hr_limit = (
            _percentile(hr_values, STRONG_FINISH_HR_PERCENTILE) if hr_values else None
        )

    indices = range(len(valid) - window, len(valid))
    for i in indices:
        pace = _as_float(valid[i].get("pace_s_per_km"))
        if pace is None or pace >= run_median:
            return set()
        if hr_limit is None:
            continue
        avg_hr = _as_float(valid[i].get("avg_hr"))
        if avg_hr is not None and avg_hr > hr_limit:
            return set()
    return set(indices)


# --- Scene assembly ---------------------------------------------------------


def _build_scenes(
    valid: Sequence[Mapping[str, Any]],
    kinds: Sequence[str | None],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
) -> list[dict[str, Any]]:
    """Merge consecutive same-kind splits into scenes, then fold walk breaks."""
    groups: list[tuple[str, list[int]]] = []
    for i, kind in enumerate(kinds):
        if kind is None:
            continue
        if groups and groups[-1][0] == kind and groups[-1][1][-1] == i - 1:
            groups[-1][1].append(i)
        else:
            groups.append((kind, [i]))

    # Breaks scattered over a long run are one story, not three: every
    # walk_break group collapses into a single scene carrying ``km_list``.
    walk_members = [
        i for kind, members in groups if kind == "walk_break" for i in members
    ]
    walk_kms = [_km(valid[i]) for i in walk_members]

    scenes: list[dict[str, Any]] = []
    walk_emitted = False
    for kind, members in groups:
        if kind == "walk_break":
            if walk_emitted:
                continue
            walk_emitted = True
            members = walk_members
        scenes.append(
            _scene(
                kind,
                valid,
                members,
                hr_ceiling=hr_ceiling,
                run_median=run_median,
                first_third_median=first_third_median,
                walk_kms=walk_kms,
            )
        )
    return scenes


def _scene(
    kind: str,
    valid: Sequence[Mapping[str, Any]],
    members: Sequence[int],
    *,
    hr_ceiling: int | None,
    run_median: float,
    first_third_median: float,
    walk_kms: Sequence[int],
) -> dict[str, Any]:
    """Build one scene dict (``id`` is assigned later, after the cap)."""
    kms = [_km(valid[i]) for i in members]
    facts = _facts(
        kind,
        valid,
        members,
        hr_ceiling=hr_ceiling,
        run_median=run_median,
        first_third_median=first_third_median,
        walk_kms=walk_kms,
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
    walk_kms: Sequence[int],
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
    elif kind == "self_correction":
        first = members[0]
        pace = _as_float(valid[first].get("pace_s_per_km"))
        prev_pace = _as_float(valid[first - 1].get("pace_s_per_km")) if first else None
        if pace is not None and prev_pace is not None:
            facts["pace_delta_s_per_km"] = _round(pace - prev_pace)
        after = members[-1] + 1
        next_hr = _as_float(valid[after].get("avg_hr")) if after < len(valid) else None
        if next_hr is not None:
            facts["next_avg_hr"] = _round(next_hr)
    elif kind == "walk_break":
        facts["km_list"] = list(walk_kms)
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
    elif kind in {"surge", "strong_finish"}:
        if paces:
            reference = min(paces) if kind == "surge" else median(paces)
            facts["pace_s_per_km"] = _round(reference)
            facts["pace_delta_s_per_km"] = _round(run_median - reference)
            facts["median_pace_s_per_km"] = _round(run_median)
        if kind == "strong_finish" and hr_ceiling is not None:
            facts["hr_ceiling"] = int(hr_ceiling)
    return facts


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


def _cap_and_number(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the ``MAX_MOMENTS`` most newsworthy scenes, back in run order."""
    ranked = sorted(scenes, key=lambda s: _priority_rank(str(s["kind"])))
    kept = ranked[:MAX_MOMENTS]
    kept.sort(key=lambda s: (s["km_from"], s["km_to"]))
    for n, scene in enumerate(kept, start=1):
        scene["id"] = f"m{n}"
    return kept


def _priority_rank(kind: str) -> int:
    """Index in :data:`_PRIORITY`; unknown kinds sort last."""
    try:
        return _PRIORITY.index(kind)
    except ValueError:
        return len(_PRIORITY)


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
