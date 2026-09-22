"""Stride and stride-recovery lap roles from the workout step index.

Strides are a short repeat group inside an easy run (Issue #1294). Garmin
records the laps of an [MCP] run step as ``ACTIVE``, so ``intensityType`` cannot
tell a 20 s stride from the jog around it. The workout step index
(``wktStepIndex``) can: every iteration of a repeat group reuses the same step
indices, so a step that comes back in two or more separate lap groups is a
repeat step. Short laps of a repeat step are strides; the longer laps of the
repeat steps in the same span are their recoveries.

The rule is pure and deterministic, so the splits and performance_trends
inserters apply the same classification to the same raw laps.
"""

from collections import Counter
from typing import Any

STRIDE_MAX_SECONDS: float = 45.0

STRIDE_ROLE = "stride"
STRIDE_RECOVERY_ROLE = "recovery"


def _is_short(lap: dict[str, Any]) -> bool:
    duration = lap.get("duration_seconds")
    return duration is not None and 0 < float(duration) <= STRIDE_MAX_SECONDS


def _step_groups(laps: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    """Maximal runs of consecutive laps sharing a step index.

    Returns ``(step_index, start_pos, end_pos_inclusive)``. A lap without a step
    index breaks a run, so two groups of the same index are never adjacent.
    """
    groups: list[tuple[int, int, int]] = []
    for pos, lap in enumerate(laps):
        step = lap.get("workout_step_index")
        if step is None:
            continue
        if groups and groups[-1][0] == step and groups[-1][2] == pos - 1:
            groups[-1] = (step, groups[-1][1], pos)
        else:
            groups.append((step, pos, pos))
    return groups


def assign_stride_roles(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return laps with role_phase rewritten for repeat-group strides.

    A lap is a stride when duration_seconds <= STRIDE_MAX_SECONDS and its
    workout_step_index recurs in >= 2 non-adjacent lap groups (a repeat
    iteration). Longer laps whose index also recurs within the same repeat
    span become 'recovery'. Laps without workout_step_index are untouched.

    The repeat span runs from the first stride to the lap group that follows the
    last stride, when that group belongs to a repeat step (the recovery of the
    final iteration). The input laps are not mutated; copies are returned.
    """
    result = [dict(lap) for lap in laps]
    groups = _step_groups(result)
    group_counts = Counter(step for step, _, _ in groups)
    repeating = {step for step, count in group_counts.items() if count >= 2}
    if not repeating:
        return result

    stride_positions = [
        pos
        for pos, lap in enumerate(result)
        if lap.get("workout_step_index") in repeating and _is_short(lap)
    ]
    if not stride_positions:
        return result

    span_start = stride_positions[0]
    last_stride = stride_positions[-1]
    span_end = last_stride
    for step, start, end in groups:
        if start > last_stride:
            if step in repeating:
                span_end = end
            break

    strides = set(stride_positions)
    for pos in range(span_start, span_end + 1):
        lap = result[pos]
        if lap.get("workout_step_index") not in repeating:
            continue
        lap["role_phase"] = STRIDE_ROLE if pos in strides else STRIDE_RECOVERY_ROLE
    return result
