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
(threshold / tempo / strides) genuinely need bookends, so they keep them — and
their reconciliation band is widened by exactly those minutes.
"""

from __future__ import annotations

from typing import Any

#: Minutes of untargeted warmup prepended to a bookended session.
WARMUP_MINUTES: int = 10

#: Minutes of untargeted cooldown appended to a bookended session.
COOLDOWN_MINUTES: int = 5

#: Session types whose Garmin workout is bookended by an untargeted
#: warmup/cooldown. Everything else is registered as a single body step.
BOOKENDED_TYPES: frozenset[str] = frozenset({"threshold", "tempo", "strides"})


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
