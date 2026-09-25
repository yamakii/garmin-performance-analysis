"""Align a prescription's steps to the laps of the run (Issue #1402, Epic #1398).

A structured watch workout stamps every lap with the FIT index of the step it
was recorded in (``workout_step_index``). :func:`align_segments` maps each
executable step of a prescription structure -- and each iteration of a repeat
-- onto the laps that carry its index, so a step can be judged against what it
asked for.

Rules:

- **Indices.** The expected indices come from
  :func:`~garmin_mcp.analysis.workout_structure.fit_step_indices`: a repeat
  group's children first, the repeat marker after them.
- **Grouping.** Laps are grouped into maximal runs of the same index; auto-lap
  may split one step across several laps.
- **Unindexed tails.** A short lap without an index (the tail between the end
  of the workout and the stop button, same rule as
  :func:`~garmin_mcp.analysis.run_moments._is_short_unindexed`) is absorbed
  into the step before it. A long unindexed stretch after the workout is
  running the watch did not cover; it becomes an ``optional`` step (a
  fast-finish branch, never registered on the watch) when the structure ends
  with one, and is left out otherwise.
- **Order.** Lap groups must follow the prescribed order. Prescribed steps the
  laps skip over are listed in ``missing`` (a skipped final recovery is listed
  but not penalised later).
- **Fingerprint.** Every indexed lap's ``intensity_type`` has to fit its step:
  ``run`` <-> ACTIVE|INTERVAL, ``recovery`` / ``rest`` <->
  RECOVERY|REST|ACTIVE, ``warmup`` <-> WARMUP|ACTIVE, ``cooldown`` <->
  COOLDOWN|ACTIVE. A structure with a ``run`` step must get at least one run
  step aligned.

When any rule fails the result is ``method="none"`` with a ``reason``;
nothing is guessed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from garmin_mcp.analysis.run_moments import _is_short_unindexed
from garmin_mcp.analysis.workout_structure import Structure, fit_step_indices


@dataclass(frozen=True)
class SegmentRun:
    """One prescribed step (one iteration of it) as it was run.

    Attributes:
        segment_id: ``"3"`` for a top-level step, ``"1#2"`` for step 1 in its
            2nd iteration (the step's FIT index, then the iteration).
        fit_index: The step's FIT ``workout_step_index``.
        iteration: 1-based occurrence of the step (``1`` for a top-level step).
        step: The prescribed step.
        split_indices: The laps (``split_index``) the step covers.
        start_s: Elapsed seconds into the run where the step starts.
        end_s: Elapsed seconds into the run where the step ends.
        distance_km: Distance covered.
        duration_s: Time taken.
        pace_s_per_km: Average pace, ``None`` without distance.
        avg_hr: Time-weighted average heart rate, ``None`` without HR.
    """

    segment_id: str
    fit_index: int
    iteration: int
    step: Mapping[str, Any]
    split_indices: tuple[int, ...]
    start_s: float
    end_s: float
    distance_km: float
    duration_s: float
    pace_s_per_km: float | None
    avg_hr: float | None


@dataclass(frozen=True)
class Alignment:
    """The prescription's steps mapped onto the run's laps.

    Attributes:
        method: ``"step_index"`` when the laps' step indices matched the
            structure, ``"none"`` when they could not be trusted.
        segments: The steps that were run, in run order.
        missing: Segment ids that were prescribed but not run.
        skipped_optional: Ids (top-level position) of optional steps not run.
        reason: Why the alignment failed, ``None`` on success.
    """

    method: Literal["step_index", "none"]
    segments: tuple[SegmentRun, ...]
    missing: tuple[str, ...]
    skipped_optional: tuple[str, ...]
    reason: str | None


#: ``step_type`` -> the lap ``intensity_type`` values it may carry.
_FINGERPRINT: dict[str, frozenset[str]] = {
    "run": frozenset({"ACTIVE", "INTERVAL"}),
    "recovery": frozenset({"RECOVERY", "REST", "ACTIVE"}),
    "rest": frozenset({"RECOVERY", "REST", "ACTIVE"}),
    "warmup": frozenset({"WARMUP", "ACTIVE"}),
    "cooldown": frozenset({"COOLDOWN", "ACTIVE"}),
}


@dataclass(frozen=True)
class _Expected:
    """One step occurrence the laps should contain, in prescribed order."""

    segment_id: str
    fit_index: int
    iteration: int
    step: Mapping[str, Any]


@dataclass
class _Lap:
    split_index: int
    step_index: int | None
    intensity: str | None
    distance_km: float
    duration_s: float
    start_s: float
    end_s: float
    avg_hr: float | None
    row: Mapping[str, Any]


def align_segments(
    structure: Structure, splits: Sequence[Mapping[str, Any]]
) -> Alignment:
    """Map every prescribed step (and repeat iteration) onto the run's laps.

    Args:
        structure: A validated prescription structure.
        splits: The run's laps in order, as the run report reads them
            (``split_index``, ``distance_km``, ``pace_s_per_km``, ``avg_hr``,
            ``intensity_type``, ``start_s`` / ``end_s`` / ``duration_s``,
            ``workout_step_index``).

    Returns:
        An :class:`Alignment`; ``method="none"`` with a ``reason`` when the
        laps carry no step index, break the prescribed order or fail the
        intensity fingerprint.
    """
    laps = _laps(splits)
    if not laps:
        return _none("the run has no laps")
    if all(lap.step_index is None for lap in laps):
        return _none("the laps carry no workout_step_index")

    groups, tail = _group(laps)
    expected = _expected(structure)

    matched: list[tuple[_Expected, list[_Lap]]] = []
    missing: list[str] = []
    cursor = 0
    for index, group in groups:
        position = next(
            (q for q in range(cursor, len(expected)) if expected[q].fit_index == index),
            None,
        )
        if position is None:
            first = next(lap for lap in group if lap.step_index is not None)
            return _none(
                f"lap {first.split_index} carries step index {index}, which "
                "does not follow the prescribed step order"
            )
        missing.extend(e.segment_id for e in expected[cursor:position])
        matched.append((expected[position], group))
        cursor = position + 1
    missing.extend(e.segment_id for e in expected[cursor:])

    for occurrence, group in matched:
        mismatch = _fingerprint_mismatch(occurrence, group)
        if mismatch is not None:
            return _none(mismatch)

    has_run = any(e.step.get("step_type") == "run" for e in expected)
    if has_run and not any(o.step.get("step_type") == "run" for o, _ in matched):
        return _none("no prescribed run step was matched by the laps")

    segments = [_segment(occurrence, group) for occurrence, group in matched]

    optional = _trailing_optional(structure)
    skipped_optional: list[str] = []
    for i, (position, step) in enumerate(optional):
        if i == 0 and tail:
            segments.append(
                _segment(
                    _Expected(
                        segment_id=str(position),
                        fit_index=_optional_fit_index(structure, position),
                        iteration=1,
                        step=step,
                    ),
                    tail,
                )
            )
        else:
            skipped_optional.append(str(position))
    skipped_optional.extend(
        str(position) for position in _other_optional(structure, optional)
    )

    return Alignment(
        method="step_index",
        segments=tuple(segments),
        missing=tuple(missing),
        skipped_optional=tuple(sorted(skipped_optional, key=int)),
        reason=None,
    )


# ----------------------------------------------------------------------------
# Laps
# ----------------------------------------------------------------------------


def _laps(splits: Sequence[Mapping[str, Any]]) -> list[_Lap]:
    """Every lap with its position on the run's own time axis."""
    laps: list[_Lap] = []
    elapsed = 0.0
    for position, split in enumerate(splits, start=1):
        distance = _as_float(split.get("distance_km")) or 0.0
        duration = _duration(split, distance)
        split_index = _as_int(split.get("split_index"))
        intensity = split.get("intensity_type")
        laps.append(
            _Lap(
                split_index=position if split_index is None else split_index,
                step_index=_as_int(split.get("workout_step_index")),
                intensity=str(intensity).strip().upper() if intensity else None,
                distance_km=distance,
                duration_s=duration,
                start_s=elapsed,
                end_s=elapsed + duration,
                avg_hr=_as_float(split.get("avg_hr")),
                row=split,
            )
        )
        elapsed += duration
    return laps


def _duration(split: Mapping[str, Any], distance: float) -> float:
    start = _as_float(split.get("start_s"))
    end = _as_float(split.get("end_s"))
    if start is not None and end is not None and end > start:
        return end - start
    duration = _as_float(split.get("duration_s"))
    if duration is not None and duration > 0:
        return duration
    pace = _as_float(split.get("pace_s_per_km"))
    return distance * pace if pace and pace > 0 else 0.0


def _group(
    laps: Sequence[_Lap],
) -> tuple[list[tuple[int, list[_Lap]]], list[_Lap]]:
    """Maximal same-index lap runs, plus the long unindexed tail after them.

    Returns ``([(step_index, laps)], tail)``. A short unindexed lap joins the
    step before it (or, at the very start, the step after it). A long
    unindexed stretch inside the workout is not any prescribed step and is
    dropped; after the last indexed lap it is the tail an optional step may
    claim.
    """
    groups: list[tuple[int, list[_Lap]]] = []
    pending: list[_Lap] = []  # short unindexed laps before the first step
    loose: list[_Lap] = []  # long unindexed laps since the last indexed lap
    for lap in laps:
        if lap.step_index is None:
            if _is_short_unindexed(lap.row) and not loose:
                if groups:
                    groups[-1][1].append(lap)
                else:
                    pending.append(lap)
            else:
                loose.append(lap)
            continue
        loose = []
        if groups and groups[-1][0] == lap.step_index:
            groups[-1][1].append(lap)
        else:
            groups.append((lap.step_index, [*pending, lap]))
            pending = []
    return groups, loose


# ----------------------------------------------------------------------------
# Expected steps
# ----------------------------------------------------------------------------


def _expected(structure: Structure) -> list[_Expected]:
    """Every registered step occurrence in the order the watch runs them."""
    by_path = {flat.path: flat for flat in fit_step_indices(structure)}
    counts: dict[int, int] = {}
    out: list[_Expected] = []

    def walk(items: Sequence[Mapping[str, Any]], path: tuple[int, ...]) -> None:
        for i, item in enumerate(items):
            item_path = (*path, i)
            if "repeat_count" in item:
                for _ in range(int(item["repeat_count"])):
                    walk(item["steps"], item_path)
                continue
            flat = by_path.get(item_path)
            if flat is None:  # optional: not registered on the watch
                continue
            counts[flat.fit_index] = counts.get(flat.fit_index, 0) + 1
            iteration = counts[flat.fit_index]
            segment_id = (
                str(flat.fit_index)
                if flat.group_path is None
                else f"{flat.fit_index}#{iteration}"
            )
            out.append(
                _Expected(
                    segment_id=segment_id,
                    fit_index=flat.fit_index,
                    iteration=iteration,
                    step=flat.step,
                )
            )

    walk(structure, ())  # type: ignore[arg-type]
    return out


def _is_optional(item: Mapping[str, Any]) -> bool:
    return "repeat_count" not in item and bool(item.get("optional"))


def _trailing_optional(structure: Structure) -> list[tuple[int, Mapping[str, Any]]]:
    """Optional top-level steps after the last registered one."""
    trailing: list[tuple[int, Mapping[str, Any]]] = []
    for position in range(len(structure) - 1, -1, -1):
        item: Mapping[str, Any] = structure[position]  # type: ignore[assignment]
        if not _is_optional(item):
            break
        trailing.append((position, item))
    trailing.reverse()
    return trailing


def _other_optional(
    structure: Structure, trailing: Sequence[tuple[int, Mapping[str, Any]]]
) -> list[int]:
    """Optional steps in the middle of the structure: never runnable here."""
    taken = {position for position, _ in trailing}
    return [
        position
        for position, item in enumerate(structure)
        if _is_optional(item) and position not in taken  # type: ignore[arg-type]
    ]


def _optional_fit_index(structure: Structure, position: int) -> int:
    """The index an optional step would follow on (one past the last step)."""
    before = [
        flat.fit_index
        for flat in fit_step_indices(structure)
        if flat.path[0] < position
    ]
    return max(before, default=-1) + 1


# ----------------------------------------------------------------------------
# Checks and aggregates
# ----------------------------------------------------------------------------


def _fingerprint_mismatch(occurrence: _Expected, group: Sequence[_Lap]) -> str | None:
    step_type = str(occurrence.step.get("step_type") or "")
    allowed = _FINGERPRINT.get(step_type)
    if allowed is None:
        return None
    for lap in group:
        if lap.step_index is None or lap.intensity is None:
            continue
        if lap.intensity not in allowed:
            return (
                f"lap {lap.split_index} is {lap.intensity} but step "
                f"{occurrence.segment_id} is a {step_type} step"
            )
    return None


def _segment(occurrence: _Expected, group: Sequence[_Lap]) -> SegmentRun:
    distance = sum(lap.distance_km for lap in group)
    duration = sum(lap.duration_s for lap in group)
    weighted = [
        (lap.avg_hr, lap.duration_s)
        for lap in group
        if lap.avg_hr is not None and lap.duration_s > 0
    ]
    weight = sum(w for _, w in weighted)
    avg_hr = (
        round(sum(hr * w for hr, w in weighted) / weight, 1) if weight > 0 else None
    )
    pace = round(duration / distance, 1) if distance > 0 and duration > 0 else None
    return SegmentRun(
        segment_id=occurrence.segment_id,
        fit_index=occurrence.fit_index,
        iteration=occurrence.iteration,
        step=occurrence.step,
        split_indices=tuple(lap.split_index for lap in group),
        start_s=round(group[0].start_s, 1),
        end_s=round(group[-1].end_s, 1),
        distance_km=round(distance, 3),
        duration_s=round(duration, 1),
        pace_s_per_km=pace,
        avg_hr=avg_hr,
    )


def _none(reason: str) -> Alignment:
    return Alignment(
        method="none", segments=(), missing=(), skipped_optional=(), reason=reason
    )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)
