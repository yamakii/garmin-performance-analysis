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
