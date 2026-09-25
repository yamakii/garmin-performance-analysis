"""Plan-check axes derived from what the prescription asked for (Issue #1404).

A prescription is judged on what each of its steps asked for numerically,
not on the same four axes for every session. The purpose of the run only
chooses the default structure and the moment policy; here it decides two
things alone: whether a short repeat inside an easy run is a set of
``strides`` (the axis id the ``plan.strides`` evidence key relies on) and
whether the single steady step is judged for ``continuity``.

Rules (one axis per kind unless noted; module constants are provisional,
calibrated on one run):

- **Ceiling-only steps** (``hr_high`` without ``hr_low``) -> one
  ``hr_ceiling`` axis. Each second is judged against the ceiling of the step
  it was run in (:func:`~garmin_mcp.analysis.hr_windows.seconds_over_varying`
  through the steady mask) and the #1357 thresholds decide:
  off plan past :data:`~garmin_mcp.analysis.derivations.HR_CEILING_OFF_PCT`
  of the judged time AND
  :data:`~garmin_mcp.analysis.derivations.HR_CEILING_OFF_SECONDS`.
- **Band steps** (both bounds) with at least :data:`BAND_MIN_WORK_S` of work
  -> ``hr_band`` (``hr_band_2``, ... for further steps). A ramp-in of
  ``min(RAMP_IN_S, RAMP_IN_SHARE x step)`` is dropped from every iteration;
  the axis is on plan when at least :data:`BAND_IN_MIN` of the rest sat in
  the band and at most :data:`BAND_ABOVE_MAX` above it.
- **Work steps shorter than** :data:`BAND_MIN_WORK_S` are never judged on HR
  (HR lags the effort): they are judged on completion, on the pace band when
  one is given and, for reps, on consistency (pace spread at most
  :data:`REP_PACE_SPREAD_MAX`).
- **Repeat groups** -> ``reps`` (``reps_2``, ...). A rep counts as done at
  :data:`REP_DONE_SHARE` of its prescribed length; only run steps are
  counted, so a skipped final recovery costs nothing. Short reps (work at
  most :data:`STRIDES_MAX_WORK_S`) inside an easy purpose keep the id
  ``strides``. Missing reps are 🟡 (severity 1), never 🔴.
- **Consecutive run steps with ascending bands** and no recovery between ->
  ``stages``: every stage in its band, the stage average HR rising (within
  :data:`STAGE_HR_TOLERANCE`) and the final stage reached.
- **Pace-band steps** -> ``pace_band``: each segment's pace within its bounds.
- **Continuity** -> only when the structure has a single top-level run step,
  and judged on that step's own laps, so warmup laps no longer set the
  established pace.
- **Alignment** ``method="none"`` -> every axis is ``insufficient``
  (severity 0). The one exception is a structure of a single step: the whole
  run *is* that step, so it is judged as such.
- **Optional steps** that were not run produce no axis.

The module is pure: no I/O, no DB access.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

from garmin_mcp.analysis.derivations import (
    HR_CEILING_OFF_PCT,
    HR_CEILING_OFF_SECONDS,
)
from garmin_mcp.analysis.hr_windows import (
    masked_mean_hr,
    seconds_in_band,
    seconds_over_varying,
)
from garmin_mcp.analysis.purpose_outcome import SUSTAIN_PURPOSES
from garmin_mcp.analysis.purpose_outcome import evaluate as evaluate_outcome
from garmin_mcp.analysis.workout_alignment import Alignment, SegmentRun
from garmin_mcp.analysis.workout_structure import Structure, fit_step_indices

AxisStatus = Literal["on_plan", "off_plan", "short", "missing", "insufficient"]

# --- Heart-rate bands ----------------------------------------------------------
#: Work shorter than this is never judged on HR: the heart has not caught up.
BAND_MIN_WORK_S = 180
#: The first seconds of a band step are the heart rising into it.
RAMP_IN_S = 90
RAMP_IN_SHARE = 0.3
#: On plan: at least this share of the judged time in the band ...
BAND_IN_MIN = 0.60
#: ... and at most this share above it.
BAND_ABOVE_MAX = 0.20

# --- Ceilings --------------------------------------------------------------------
#: Without a time series a segment's average HR may sit this far above its
#: ceiling and still count as kept (the verdict's ``hr_tolerance_bpm``).
CEILING_AVG_TOLERANCE_BPM = 3

# --- Reps ------------------------------------------------------------------------
#: A rep counts as done at this share of its prescribed length.
REP_DONE_SHARE = 0.8
#: Short reps are consistent when (slowest - fastest) / median pace stays below.
REP_PACE_SPREAD_MAX = 0.05
#: Reps this short inside an easy run are strides.
STRIDES_MAX_WORK_S = 45
#: Purposes whose short repeats are strides.
EASY_PURPOSES: frozenset[str] = frozenset({"easy", "recovery", "long_easy"})

# --- Stages ----------------------------------------------------------------------
#: A stage's average HR may sit this far below the previous one and still rise.
STAGE_HR_TOLERANCE = 1

#: Step types never judged on HR (the heart is coming down from the work).
_UNJUDGED_HR_TYPES: frozenset[str] = frozenset({"recovery", "rest"})

_TYPE_LABELS: dict[str, str] = {
    "warmup": "ウォームアップ",
    "run": "メイン",
    "recovery": "リカバリー",
    "rest": "休息",
    "cooldown": "クールダウン",
}


@dataclass(frozen=True)
class AxisResult:
    """One plan-check axis.

    Attributes:
        axis: Unique id (``hr_ceiling``, ``hr_band``, ``hr_band_2``,
            ``pace_band``, ``reps``, ``strides``, ``stages``, ``continuity``).
        label_ja: Japanese name of the axis.
        target: What was asked for (Japanese / numbers).
        actual: What was run.
        status: ``on_plan`` / ``off_plan`` / ``short`` / ``missing`` /
            ``insufficient``.
        severity: ``0`` on plan or insufficient, ``1`` a deviation, ``2`` a
            risk-side deviation.
        segments: Per-segment detail ``{segment_id, label, target, actual,
            in_band_pct?, on_plan}``.
    """

    axis: str
    label_ja: str
    target: str
    actual: str
    status: AxisStatus
    severity: int
    segments: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _Entry:
    """One prescribed step and the segments it was run as."""

    path: tuple[int, ...]
    step: Mapping[str, Any]
    expected: int
    in_group: bool
    optional: bool
    segments: tuple[SegmentRun, ...]

    @property
    def step_type(self) -> str:
        return str(self.step.get("step_type") or "")


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------


def evaluate_structure_axes(
    structure: Structure,
    alignment: Alignment,
    *,
    splits: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
    steady: Sequence[bool] | None,
    purpose: str,
) -> list[AxisResult]:
    """Derive and judge the plan-check axes of one run.

    Args:
        structure: The prescription's validated step structure.
        alignment: The structure aligned to the run's laps
            (:func:`~garmin_mcp.analysis.workout_alignment.align_segments`).
        splits: The run's laps (``split_index``, ``distance_km``,
            ``pace_s_per_km``, ``avg_hr``, timing), as the alignment read them.
        samples: The run's time series (``timestamp_s``, ``heart_rate``) on
            the same time axis as the segments; may be empty.
        steady: The steady mask over ``samples``
            (:func:`~garmin_mcp.analysis.hr_windows.steady_mask`), or ``None``
            to judge every sample.
        purpose: The run's resolved purpose id.

    Returns:
        The axes in a fixed order: ``hr_ceiling``, ``stages``, ``hr_band*``,
        ``pace_band``, ``reps*`` / ``strides``, ``continuity``.
    """
    entries, aligned = _entries(structure, alignment, splits)
    mask = list(steady) if steady is not None else [True] * len(samples)
    times = [float(sample["timestamp_s"]) for sample in samples]
    ctx = _Context(samples=samples, mask=mask, times=times, insufficient=not aligned)

    stage_paths = _stage_paths(structure)
    axes: list[AxisResult] = []

    ceiling = _ceiling_axis(entries, ctx)
    if ceiling is not None:
        axes.append(ceiling)

    stage_entries = [e for e in entries if e.path in stage_paths]
    if stage_entries:
        axes.append(_stages_axis(stage_entries, ctx))

    band_entries = [
        e
        for e in entries
        if _is_band(e.step)
        and e.path not in stage_paths
        and e.step_type not in _UNJUDGED_HR_TYPES
        and (_work_seconds(e) or 0.0) >= BAND_MIN_WORK_S
    ]
    for number, entry in enumerate(band_entries, start=1):
        axis_id = "hr_band" if number == 1 else f"hr_band_{number}"
        axes.append(_band_axis(axis_id, entry, ctx))

    pace = _pace_axis(entries, ctx)
    if pace is not None:
        axes.append(pace)

    axes.extend(_reps_axes(structure, entries, purpose, ctx))

    continuity = _continuity_axis(entries, splits, purpose, ctx)
    if continuity is not None:
        axes.append(continuity)
    return axes


@dataclass(frozen=True)
class _Context:
    samples: Sequence[Mapping[str, Any]]
    mask: list[bool]
    times: list[float]
    insufficient: bool

    def window(self, start: float, end: float, *, steady: bool) -> list[bool]:
        """Mask of the samples in ``[start, end)`` (and the steady ones)."""
        lo = bisect.bisect_left(self.times, start)
        hi = bisect.bisect_left(self.times, end)
        out = [False] * len(self.samples)
        for index in range(lo, hi):
            out[index] = self.mask[index] if steady and index < len(self.mask) else True
        return out


# ----------------------------------------------------------------------------
# Entries
# ----------------------------------------------------------------------------


def _entries(
    structure: Structure,
    alignment: Alignment,
    splits: Sequence[Mapping[str, Any]],
) -> tuple[list[_Entry], bool]:
    """Every step to judge with its segments, and whether they are aligned.

    Optional steps enter only when they were run.
    """
    flats = fit_step_indices(structure)
    segments = list(alignment.segments)
    aligned = alignment.method != "none"
    has_optional = any(_is_optional(item) for item in structure)  # type: ignore[arg-type]
    if not aligned and len(flats) == 1 and not has_optional:
        whole = _whole_run_segment(flats[0].fit_index, flats[0].step, splits)
        if whole is not None:
            segments = [whole]
            aligned = True

    entries: list[_Entry] = []
    for flat in flats:
        entries.append(
            _Entry(
                path=flat.path,
                step=flat.step,
                expected=flat.repeat_count,
                in_group=flat.group_path is not None,
                optional=False,
                segments=tuple(
                    s
                    for s in segments
                    if s.fit_index == flat.fit_index and not s.step.get("optional")
                ),
            )
        )
    for position, item in enumerate(structure):
        if not _is_optional(item):  # type: ignore[arg-type]
            continue
        ran = tuple(
            s
            for s in segments
            if s.step.get("optional") and s.segment_id == str(position)
        )
        if ran:
            entries.append(
                _Entry(
                    path=(position,),
                    step=item,  # type: ignore[arg-type]
                    expected=1,
                    in_group=False,
                    optional=True,
                    segments=ran,
                )
            )
    entries.sort(key=lambda e: e.path)
    return entries, aligned


def _is_optional(item: Mapping[str, Any]) -> bool:
    return "repeat_count" not in item and bool(item.get("optional"))


def _whole_run_segment(
    fit_index: int, step: Mapping[str, Any], splits: Sequence[Mapping[str, Any]]
) -> SegmentRun | None:
    """The whole run as the one step of a single-step structure."""
    if not splits:
        return None
    indices: list[int] = []
    distance = 0.0
    duration = 0.0
    hr_weighted = 0.0
    hr_weight = 0.0
    for position, split in enumerate(splits, start=1):
        km = _num(split.get("distance_km")) or 0.0
        seconds = _lap_seconds(split, km)
        indices.append(_split_index(split, position))
        distance += km
        duration += seconds
        hr = _num(split.get("avg_hr"))
        if hr is not None and seconds > 0:
            hr_weighted += hr * seconds
            hr_weight += seconds
    return SegmentRun(
        segment_id=str(fit_index),
        fit_index=fit_index,
        iteration=1,
        step=step,
        split_indices=tuple(indices),
        start_s=0.0,
        end_s=round(duration, 1),
        distance_km=round(distance, 3),
        duration_s=round(duration, 1),
        pace_s_per_km=(
            round(duration / distance, 1) if distance > 0 and duration > 0 else None
        ),
        avg_hr=round(hr_weighted / hr_weight, 1) if hr_weight > 0 else None,
    )


# ----------------------------------------------------------------------------
# hr_ceiling
# ----------------------------------------------------------------------------


def _ceiling_axis(entries: Sequence[_Entry], ctx: _Context) -> AxisResult | None:
    ceiling_entries = [
        e
        for e in entries
        if e.step.get("hr_high") is not None
        and e.step.get("hr_low") is None
        and e.step_type not in _UNJUDGED_HR_TYPES
    ]
    if not ceiling_entries:
        return None
    ceilings = sorted({int(e.step["hr_high"]) for e in ceiling_entries})
    target = (
        f"{ceilings[0]} bpm 以下"
        if len(ceilings) == 1
        else f"区間別 {'/'.join(map(str, ceilings))} bpm 以下"
    )
    runs = [(s, int(e.step["hr_high"])) for e in ceiling_entries for s in e.segments]
    if ctx.insufficient or not runs:
        return _insufficient("hr_ceiling", "心拍上限", target)

    per_sample: list[int | None] = [None] * len(ctx.samples)
    details: list[dict[str, Any]] = []
    for segment, ceiling in runs:
        window = ctx.window(segment.start_s, segment.end_s, steady=True)
        ceilings_in = [ceiling if keep else None for keep in window]
        for index, keep in enumerate(window):
            if keep:
                per_sample[index] = ceiling
        over = seconds_over_varying(ctx.samples, ctx.mask, ceilings_in)
        details.append(_ceiling_detail(segment, ceiling, over))

    total = seconds_over_varying(ctx.samples, ctx.mask, per_sample)
    if total is not None:
        off = (
            total["pct_over"] > HR_CEILING_OFF_PCT
            and total["seconds_over"] >= HR_CEILING_OFF_SECONDS
        )
        actual = f"超過 {_clock(total['seconds_over'])}（{total['pct_over']:g}%）"
        return _result("hr_ceiling", "心拍上限", target, actual, off, details)

    # No time series: each segment's average against its own ceiling.
    judged = [d for d in details if d["avg_hr"] is not None]
    if not judged:
        return _insufficient("hr_ceiling", "心拍上限", target)
    off = any(not d["on_plan"] for d in judged)
    actual = "、".join(f"{d['avg_hr']:.0f}" for d in judged) + " bpm（区間平均）"
    return _result("hr_ceiling", "心拍上限", target, actual, off, details)


def _ceiling_detail(
    segment: SegmentRun, ceiling: int, over: Mapping[str, float] | None
) -> dict[str, Any]:
    if over is not None:
        on_plan = not (
            over["pct_over"] > HR_CEILING_OFF_PCT
            and over["seconds_over"] >= HR_CEILING_OFF_SECONDS
        )
        actual = f"超過 {_clock(over['seconds_over'])}（{over['pct_over']:g}%）"
    else:
        on_plan = (
            segment.avg_hr is None
            or segment.avg_hr - ceiling <= CEILING_AVG_TOLERANCE_BPM
        )
        actual = "-" if segment.avg_hr is None else f"平均 {segment.avg_hr:.0f} bpm"
    return {
        "segment_id": segment.segment_id,
        "label": _segment_label(segment),
        "target": f"{ceiling} bpm 以下",
        "actual": actual,
        "avg_hr": segment.avg_hr,
        "on_plan": on_plan,
    }


# ----------------------------------------------------------------------------
# hr_band
# ----------------------------------------------------------------------------


def _band_axis(axis_id: str, entry: _Entry, ctx: _Context) -> AxisResult:
    low = int(entry.step["hr_low"])
    high = int(entry.step["hr_high"])
    target = f"{low}-{high} bpm"
    if ctx.insufficient:
        return _insufficient(axis_id, "心拍帯", target)
    if not entry.segments:
        return _missing(axis_id, "心拍帯", target)

    details: list[dict[str, Any]] = []
    seconds_in = seconds_above = seconds_total = 0.0
    fallback_off = False
    fallback_judged = False
    for segment in entry.segments:
        length = _prescribed_seconds(entry.step) or segment.duration_s
        ramp = min(RAMP_IN_S, RAMP_IN_SHARE * length)
        window = ctx.window(segment.start_s + ramp, segment.end_s, steady=False)
        band = seconds_in_band(ctx.samples, window, low, high)
        detail: dict[str, Any] = {
            "segment_id": segment.segment_id,
            "label": _segment_label(segment),
            "target": target,
        }
        if band is not None:
            seconds_in += band["seconds_in"]
            seconds_above += band["seconds_above"]
            seconds_total += (
                band["seconds_in"] + band["seconds_above"] + band["seconds_below"]
            )
            detail["actual"] = f"帯内 {band['pct_in']:g}%（上 {band['pct_above']:g}%）"
            detail["in_band_pct"] = band["pct_in"]
            detail["on_plan"] = _band_on_plan(band["pct_in"], band["pct_above"])
        elif segment.avg_hr is not None:
            fallback_judged = True
            in_band = low <= segment.avg_hr <= high
            fallback_off = fallback_off or not in_band
            detail["actual"] = f"平均 {segment.avg_hr:.0f} bpm"
            detail["on_plan"] = in_band
        else:
            detail["actual"] = "-"
            detail["on_plan"] = False
        details.append(detail)

    if seconds_total > 0:
        pct_in = round(seconds_in / seconds_total * 100.0, 1)
        pct_above = round(seconds_above / seconds_total * 100.0, 1)
        actual = f"帯内 {pct_in:g}%（上 {pct_above:g}%）"
        off = not _band_on_plan(pct_in, pct_above)
        return _result(axis_id, "心拍帯", target, actual, off, details)
    if fallback_judged:
        actual = "、".join(d["actual"] for d in details if d["actual"] != "-")
        return _result(axis_id, "心拍帯", target, actual, fallback_off, details)
    return _insufficient(axis_id, "心拍帯", target)


def _band_on_plan(pct_in: float, pct_above: float) -> bool:
    return pct_in / 100.0 >= BAND_IN_MIN and pct_above / 100.0 <= BAND_ABOVE_MAX


# ----------------------------------------------------------------------------
# stages
# ----------------------------------------------------------------------------


def _stage_paths(structure: Structure) -> set[tuple[int, ...]]:
    """Paths of the first run of top-level run steps with ascending bands."""
    run: list[tuple[int, Mapping[str, Any]]] = []
    candidates: list[list[tuple[int, Mapping[str, Any]]]] = []
    for position, raw in enumerate(structure):
        item: Mapping[str, Any] = raw  # type: ignore[assignment]
        if (
            "repeat_count" not in item
            and not item.get("optional")
            and item.get("step_type") == "run"
            and _is_band(item)
        ):
            run.append((position, item))
            continue
        candidates.append(run)
        run = []
    candidates.append(run)
    for steps in candidates:
        if len(steps) >= 2 and _ascending([step for _, step in steps]):
            return {(position,) for position, _ in steps}
    return set()


def _ascending(steps: Sequence[Mapping[str, Any]]) -> bool:
    lows = [int(step["hr_low"]) for step in steps]
    highs = [int(step["hr_high"]) for step in steps]
    non_decreasing = all(
        b_lo >= a_lo and b_hi >= a_hi
        for a_lo, b_lo, a_hi, b_hi in zip(
            lows, lows[1:], highs, highs[1:], strict=False
        )
    )
    return non_decreasing and (lows[-1] > lows[0] or highs[-1] > highs[0])


def _stages_axis(entries: Sequence[_Entry], ctx: _Context) -> AxisResult:
    bands = [(int(e.step["hr_low"]), int(e.step["hr_high"])) for e in entries]
    target = " → ".join(f"{lo}-{hi}" for lo, hi in bands) + " bpm"
    if ctx.insufficient:
        return _insufficient("stages", "段階的ビルドアップ", target)

    stage_hr: list[float | None] = []
    details: list[dict[str, Any]] = []
    for number, (entry, (low, high)) in enumerate(
        zip(entries, bands, strict=True), start=1
    ):
        segment = entry.segments[0] if entry.segments else None
        hr = None if segment is None else _stage_hr(entry, segment, ctx)
        stage_hr.append(hr)
        details.append(
            {
                "segment_id": segment.segment_id if segment else str(entry.path[0]),
                "label": f"第{number}段",
                "target": f"{low}-{high} bpm",
                "actual": "未実施" if segment is None else _bpm(hr),
                "on_plan": hr is not None and low <= hr <= high,
            }
        )

    ran = [hr for hr in stage_hr if hr is not None]
    if not ran:
        return _insufficient("stages", "段階的ビルドアップ", target)

    problems: list[str] = []
    last = len(entries)
    for number, (hr, (low, high)) in enumerate(zip(stage_hr, bands, strict=True), 1):
        if number == last:
            if hr is None:
                problems.append("最終段 未到達")
            elif hr < low:
                problems.append(f"最終段 {hr:.0f} < {low}")
            elif hr > high:
                problems.append(f"最終段 {hr:.0f} > {high}")
        elif hr is None:
            problems.append(f"第{number}段 未実施")
        elif not low <= hr <= high:
            problems.append(f"第{number}段 {hr:.0f}（帯 {low}-{high}）")
    previous: tuple[int, float] | None = None
    for number, hr in enumerate(stage_hr, start=1):
        if hr is None:
            continue
        if previous is not None and hr < previous[1] - STAGE_HR_TOLERANCE:
            problems.append(
                f"第{number}段 {hr:.0f} が第{previous[0]}段 {previous[1]:.0f} より低下"
            )
        previous = (number, hr)

    chain = " → ".join("-" if hr is None else f"{hr:.0f}" for hr in stage_hr) + " bpm"
    actual = f"{chain}（{'、'.join(problems)}）" if problems else chain
    return _result(
        "stages", "段階的ビルドアップ", target, actual, bool(problems), details
    )


def _stage_hr(entry: _Entry, segment: SegmentRun, ctx: _Context) -> float | None:
    """A stage's average HR past its ramp-in, else the laps' average."""
    if ctx.samples:
        length = _prescribed_seconds(entry.step) or segment.duration_s
        ramp = min(RAMP_IN_S, RAMP_IN_SHARE * length)
        window = ctx.window(segment.start_s + ramp, segment.end_s, steady=False)
        hr = masked_mean_hr(ctx.samples, window)
        if hr is not None:
            return hr
    return segment.avg_hr


# ----------------------------------------------------------------------------
# pace_band
# ----------------------------------------------------------------------------


def _pace_axis(entries: Sequence[_Entry], ctx: _Context) -> AxisResult | None:
    paced = [
        e
        for e in entries
        if e.step.get("pace_low_s_per_km") is not None
        or e.step.get("pace_high_s_per_km") is not None
    ]
    if not paced:
        return None
    bands = sorted({_pace_band_text(e.step) for e in paced})
    target = bands[0] if len(bands) == 1 else "区間別 " + " / ".join(bands)
    if ctx.insufficient:
        return _insufficient("pace_band", "ペース帯", target)

    details: list[dict[str, Any]] = []
    for entry in paced:
        low = _num(entry.step.get("pace_low_s_per_km"))
        high = _num(entry.step.get("pace_high_s_per_km"))
        for segment in entry.segments:
            pace = segment.pace_s_per_km
            within = (
                pace is not None
                and (low is None or pace >= low)
                and (high is None or pace <= high)
            )
            details.append(
                {
                    "segment_id": segment.segment_id,
                    "label": _segment_label(segment),
                    "target": _pace_band_text(entry.step),
                    "actual": "-" if pace is None else _pace(pace),
                    "pace_s_per_km": pace,
                    "on_plan": within,
                }
            )
    judged = [d for d in details if d["pace_s_per_km"] is not None]
    if not details:
        return _missing("pace_band", "ペース帯", target)
    if not judged:
        return _insufficient("pace_band", "ペース帯", target)
    off = [d for d in judged if not d["on_plan"]]
    if off:
        actual = "、".join(
            f"{d['label']} {d['actual']}（帯 {d['target']}）" for d in off
        )
    else:
        actual = "、".join(d["actual"] for d in judged)
    return _result("pace_band", "ペース帯", target, actual, bool(off), details)


# ----------------------------------------------------------------------------
# reps / strides
# ----------------------------------------------------------------------------


def _reps_axes(
    structure: Structure, entries: Sequence[_Entry], purpose: str, ctx: _Context
) -> list[AxisResult]:
    axes: list[AxisResult] = []
    reps_number = 0
    for position, item in enumerate(structure):
        if "repeat_count" not in item:
            continue
        work = [
            e
            for e in entries
            if e.in_group and e.path[0] == position and e.step_type == "run"
        ]
        if not work:
            continue
        work_seconds = [_work_seconds(e) for e in work]
        is_strides = purpose in EASY_PURPOSES and all(
            s is not None and s <= STRIDES_MAX_WORK_S for s in work_seconds
        )
        short = all(s is not None and s < BAND_MIN_WORK_S for s in work_seconds)
        if is_strides:
            axis_id = "strides"
        else:
            reps_number += 1
            axis_id = "reps" if reps_number == 1 else f"reps_{reps_number}"
        axes.append(
            _reps_axis(axis_id, work, check_spread=short and not is_strides, ctx=ctx)
        )
    return axes


def _reps_axis(
    axis_id: str, work: Sequence[_Entry], *, check_spread: bool, ctx: _Context
) -> AxisResult:
    strides = axis_id == "strides"
    label = "ウインドスプリント" if strides else "本数"
    expected = sum(e.expected for e in work)
    lengths = sorted({_length_text(e.step) for e in work})
    target = f"{expected}本" if strides else f"{expected}本 × {' / '.join(lengths)}"
    if check_spread:
        target += f"（ペース差 {REP_PACE_SPREAD_MAX * 100:g}% 以内）"
    if ctx.insufficient:
        return _insufficient(axis_id, label, target)

    details: list[dict[str, Any]] = []
    done_paces: list[float] = []
    done = 0
    for entry in work:
        for segment in entry.segments:
            complete = _rep_done(entry.step, segment)
            done += int(complete)
            if complete and segment.pace_s_per_km is not None:
                done_paces.append(segment.pace_s_per_km)
            details.append(
                {
                    "segment_id": segment.segment_id,
                    "label": _segment_label(segment),
                    "target": _length_text(entry.step),
                    "actual": _clock(segment.duration_s)
                    + (
                        f"（{_pace(segment.pace_s_per_km)}）"
                        if segment.pace_s_per_km is not None
                        else ""
                    ),
                    "on_plan": complete,
                }
            )
    done = min(done, expected)

    spread: float | None = None
    if check_spread and len(done_paces) >= 2:
        spread = (max(done_paces) - min(done_paces)) / median(done_paces)

    actual = f"{done}本" if strides else f"{done}/{expected}本"
    if spread is not None:
        actual += f"、ペース差 {spread * 100:.1f}%"

    if done < expected:
        status: AxisStatus = "short" if done > 0 else "missing"
        return AxisResult(axis_id, label, target, actual, status, 1, tuple(details))
    off = spread is not None and spread > REP_PACE_SPREAD_MAX
    return _result(axis_id, label, target, actual, off, details)


def _rep_done(step: Mapping[str, Any], segment: SegmentRun) -> bool:
    """Whether one run of a rep covered :data:`REP_DONE_SHARE` of its length."""
    if "distance_m" in step:
        return segment.distance_km * 1000 >= REP_DONE_SHARE * float(step["distance_m"])
    seconds = _prescribed_seconds(step)
    if seconds is None:
        return True
    return segment.duration_s >= REP_DONE_SHARE * seconds


# ----------------------------------------------------------------------------
# continuity
# ----------------------------------------------------------------------------


def _continuity_axis(
    entries: Sequence[_Entry],
    splits: Sequence[Mapping[str, Any]],
    purpose: str,
    ctx: _Context,
) -> AxisResult | None:
    steady_steps = [
        e for e in entries if not e.in_group and not e.optional and e.step_type == "run"
    ]
    if len(steady_steps) != 1 or purpose not in SUSTAIN_PURPOSES:
        return None
    target = "最後まで走り続ける"
    entry = steady_steps[0]
    if ctx.insufficient or not entry.segments:
        return _insufficient("continuity", "継続", target)

    covered = {i for segment in entry.segments for i in segment.split_indices}
    step_splits = [
        split
        for position, split in enumerate(splits, start=1)
        if _split_index(split, position) in covered
    ]
    outcome = evaluate_outcome(purpose, step_splits)
    if outcome is None:
        return _insufficient("continuity", "継続", target)
    actual = "保てた" if outcome.met else f"{outcome.breakdown_from_km:g} km から崩れ"
    detail = {
        "segment_id": entry.segments[0].segment_id,
        "label": _segment_label(entry.segments[0]),
        "target": target,
        "actual": actual,
        "on_plan": outcome.met,
    }
    return _result("continuity", "継続", target, actual, not outcome.met, [detail])


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _result(
    axis: str,
    label: str,
    target: str,
    actual: str,
    off: bool,
    details: Sequence[Mapping[str, Any]],
) -> AxisResult:
    return AxisResult(
        axis=axis,
        label_ja=label,
        target=target,
        actual=actual,
        status="off_plan" if off else "on_plan",
        severity=1 if off else 0,
        segments=tuple(details),
    )


def _insufficient(axis: str, label: str, target: str) -> AxisResult:
    return AxisResult(axis, label, target, "-", "insufficient", 0, ())


def _missing(axis: str, label: str, target: str) -> AxisResult:
    return AxisResult(axis, label, target, "未実施", "missing", 1, ())


def _is_band(step: Mapping[str, Any]) -> bool:
    return step.get("hr_low") is not None and step.get("hr_high") is not None


def _prescribed_seconds(step: Mapping[str, Any]) -> float | None:
    """The step's prescribed length in seconds (distance through its pace)."""
    if "duration_minutes" in step:
        return float(step["duration_minutes"]) * 60.0
    if "duration_seconds" in step:
        return float(step["duration_seconds"])
    if "distance_m" in step:
        pace = step.get("pace_high_s_per_km") or step.get("pace_low_s_per_km")
        if pace:
            return float(step["distance_m"]) / 1000.0 * float(pace)
    return None


def _work_seconds(entry: _Entry) -> float | None:
    """How long one run of the step lasts: prescribed, else as run."""
    prescribed = _prescribed_seconds(entry.step)
    if prescribed is not None:
        return prescribed
    ran = [s.duration_s for s in entry.segments if s.duration_s > 0]
    return float(median(ran)) if ran else None


def _segment_label(segment: SegmentRun) -> str:
    step = segment.step
    base = str(step.get("label") or _TYPE_LABELS.get(str(step.get("step_type")), ""))
    if "#" in segment.segment_id:
        return f"{base} {segment.iteration}本目"
    return base


def _length_text(step: Mapping[str, Any]) -> str:
    if "distance_m" in step:
        return f"{int(step['distance_m'])}m"
    seconds = _prescribed_seconds(step)
    return "-" if seconds is None else _clock(seconds)


def _pace_band_text(step: Mapping[str, Any]) -> str:
    low = _num(step.get("pace_low_s_per_km"))
    high = _num(step.get("pace_high_s_per_km"))
    if low is not None and high is not None:
        return f"{_clock(low)}-{_clock(high)}/km"
    if high is not None:
        return f"{_clock(high)}/km 以内"
    return f"{_clock(low or 0.0)}/km 以上"


def _pace(seconds_per_km: float) -> str:
    return f"{_clock(seconds_per_km)}/km"


def _bpm(hr: float | None) -> str:
    return "-" if hr is None else f"{hr:.0f} bpm"


def _clock(seconds: float) -> str:
    """``"5:00"`` / ``"1:04:09"``."""
    total = max(0, round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _lap_seconds(split: Mapping[str, Any], distance_km: float) -> float:
    start = _num(split.get("start_s"))
    end = _num(split.get("end_s"))
    if start is not None and end is not None and end > start:
        return end - start
    duration = _num(split.get("duration_s"))
    if duration is not None and duration > 0:
        return duration
    pace = _num(split.get("pace_s_per_km"))
    return distance_km * pace if pace and pace > 0 else 0.0


def _split_index(split: Mapping[str, Any], position: int) -> int:
    """The lap's ``split_index``, else its 1-based position (as aligned)."""
    value = _num(split.get("split_index"))
    return position if value is None else int(value)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN
