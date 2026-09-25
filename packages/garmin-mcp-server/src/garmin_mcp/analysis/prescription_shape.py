"""Shape of a prescription-derived Garmin workout (#1039).

The workout builder (``tools.workout_scheduling.build_steps_from_prescription``)
and the reconciler (``analysis.prescription_reconcile``) have to agree on one
thing: how much running a registered workout adds on top of the prescribed
target. Keeping that shape here means the builder can never grow a bookend the
reconciler does not subtract (the #981/#1039 bug: a 45-min easy prescription was
registered as a 60-min workout and then graded ``replaced`` at 1.33x).

Z2 / easy / recovery / long runs are warmup intensity end to end and their HR
target is ceiling-only (#979), so a separate untargeted warmup step is
redundant: the body step already allows an easy start. Quality sessions
(threshold / tempo) genuinely need bookends, so they keep them — and their
reconciliation band is widened by exactly those minutes.

Strides are not a session of their own but an optional add-on of an easy run
(Issue #1295): a neuromuscular stimulus, not an interval. The easy row keeps
``target_minutes`` as the **total**, and the strides block sits between an
opening easy segment of at least :data:`MIN_OPENING_EASY_MINUTES` and a final
:data:`FINAL_EASY_MINUTES` of easy running, so the watch workout adds nothing
on top of the prescribed minutes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Minutes of untargeted warmup prepended to a bookended session.
WARMUP_MINUTES: int = 10

#: Minutes of untargeted cooldown appended to a bookended session.
COOLDOWN_MINUTES: int = 5

#: Session types whose Garmin workout is bookended by an untargeted
#: warmup/cooldown. Everything else is registered as a single body step.
BOOKENDED_TYPES: frozenset[str] = frozenset({"threshold", "tempo"})

#: Minutes of easy running after the strides block of an easy run.
FINAL_EASY_MINUTES: int = 5

#: Minimum minutes of easy running before the strides block of an easy run.
MIN_OPENING_EASY_MINUTES: int = 5

#: Defaults of an easy row's ``strides`` add-on (seconds per stride / per jog).
STRIDES_DEFAULT_RUN_SECONDS: int = 20
STRIDES_DEFAULT_RECOVERY_SECONDS: int = 90


def strides_block_seconds(strides: Mapping[str, Any]) -> int:
    """Return the length of a strides block: ``reps * (run + recovery)``.

    Missing ``run_seconds`` / ``recovery_seconds`` fall back to the defaults
    (:data:`STRIDES_DEFAULT_RUN_SECONDS` / :data:`STRIDES_DEFAULT_RECOVERY_SECONDS`).

    Args:
        strides: The ``strides`` object of an easy prescription row.

    Returns:
        Seconds the whole repeat group takes.
    """
    run = strides.get("run_seconds")
    recovery = strides.get("recovery_seconds")
    run_seconds = int(run) if run is not None else STRIDES_DEFAULT_RUN_SECONDS
    recovery_seconds = (
        int(recovery) if recovery is not None else STRIDES_DEFAULT_RECOVERY_SECONDS
    )
    return int(strides["reps"]) * (run_seconds + recovery_seconds)


def bookend_minutes(session_type: str | None) -> int:
    """Return the minutes a registered workout adds on top of ``target_minutes``.

    Args:
        session_type: A ``weekly_prescriptions`` session type (may be ``None``).

    Returns:
        ``WARMUP_MINUTES + COOLDOWN_MINUTES`` for :data:`BOOKENDED_TYPES`,
        otherwise ``0``.
    """
    if session_type in BOOKENDED_TYPES:
        return WARMUP_MINUTES + COOLDOWN_MINUTES
    return 0


def expected_minutes(row: Mapping[str, Any]) -> float | None:
    """Return the minutes a prescription row asks for, bookends included.

    ``target_minutes`` counts the body of a quality session only, while the
    workout on the watch — and so the run it produces — carries its
    warmup/cooldown on top. Everything that compares a run's duration with a
    prescription (the reconciler, the plan verdict, the plan card) must add
    the same bookends, or a 20-minute threshold run done exactly as registered
    reads 175% (Issue #1399).

    Prefers ``registered_bookend_minutes`` — what the workout actually put on
    the calendar carries (Issue #1087) — over the constant
    :func:`bookend_minutes` for the session type. Rows registered before that
    column existed, and rows never registered, hold ``None`` and fall back to
    the constant.

    Args:
        row: A ``weekly_prescriptions`` row (``target_minutes``,
            ``session_type``, optional ``registered_bookend_minutes``).

    Returns:
        ``target_minutes`` plus the bookend minutes, or ``None`` when the row
        names no ``target_minutes``.
    """
    target = row.get("target_minutes")
    if target is None:
        return None
    recorded = row.get("registered_bookend_minutes")
    bookends = (
        float(recorded)
        if recorded is not None
        else float(bookend_minutes(row.get("session_type")))
    )
    return float(target) + bookends


#: Step types that bookend a session rather than being part of its body.
_BOOKEND_STEP_TYPES: frozenset[str] = frozenset({"warmup", "cooldown"})


def bookend_minutes_from_steps(steps: list[dict[str, Any]] | None) -> int | None:
    """Return the warmup/cooldown minutes carried by a concrete steps array.

    :func:`bookend_minutes` answers the same question from the session type
    alone, which is right only for the workout
    ``tools.workout_scheduling.build_steps_from_prescription`` builds. A
    hand-built registration — a buildup with a different HR zone per kilometre
    cannot be expressed as one body step — may carry different bookends, and
    the 2026-09-09 tempo did: a 10-minute cooldown, so 20 minutes rather than
    the constant 15 (Issue #1087). Recording this on the row lets the
    reconciler judge against what was actually registered.

    Only top-level ``warmup`` / ``cooldown`` steps count, and only their time:
    a distance-based bookend has no minutes to add, and a repeat group is body
    work whatever it contains.

    Args:
        steps: The generic steps array a workout was registered from.

    Returns:
        Whole minutes of warmup + cooldown, or ``None`` when ``steps`` is empty
        or missing — the caller then has nothing to record and the constant
        stays in charge.
    """
    if not steps:
        return None
    total_seconds = 0.0
    for step in steps:
        if str(step.get("step_type", "")) not in _BOOKEND_STEP_TYPES:
            continue
        if "duration_minutes" in step:
            total_seconds += float(step["duration_minutes"]) * 60
        elif "duration_seconds" in step:
            total_seconds += float(step["duration_seconds"])
    return int(round(total_seconds / 60))
