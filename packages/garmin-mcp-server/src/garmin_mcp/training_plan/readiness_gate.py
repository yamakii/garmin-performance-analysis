"""Readiness gate: downgrade quality workouts when daily wellness deviates.

A pure function that consumes the personal-baseline deviation flag produced by
``get_wellness_baseline_deviation`` (#555) and downgrades the *quality* workouts
(tempo/threshold/interval/repetition) in the leading weeks of a plan to
easy/recovery. ``workout_type`` is the only intensity enum on
:class:`PlannedWorkout`, so the gate simply rewrites it before the plan is saved.

The function is side-effect free: it returns a new workout list (changed
workouts are copied) plus a list of Japanese adjustment notes for the coach to
surface to the user.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp.training_plan.models import PlannedWorkout, WorkoutType

# Quality workout type -> downgraded type. Keys are the only types affected by
# the gate; easy/recovery/long_run/race_pace/rest are intentionally absent.
DOWNGRADE_MAP: dict[str, str] = {
    "tempo": "easy",
    "threshold": "easy",
    "interval": "recovery",
    "repetition": "recovery",
}


def apply_readiness_gate(
    deviation: dict[str, Any],
    workouts: list[PlannedWorkout],
    *,
    weeks_to_check: int = 1,
) -> tuple[list[PlannedWorkout], list[str]]:
    """Downgrade quality workouts in the leading weeks when readiness is low.

    When ``deviation['overall_flag']`` is True (HRV below the personal band or
    RHR elevated), every quality workout (a key of :data:`DOWNGRADE_MAP`) within
    the first ``weeks_to_check`` weeks is downgraded to easy/recovery. Workouts
    of type easy/recovery/long_run/race_pace/rest are left unchanged.

    Args:
        deviation: Return value of ``get_wellness_baseline_deviation`` (uses the
            ``overall_flag`` key).
        workouts: Planned workouts to evaluate.
        weeks_to_check: Number of leading weeks (by ``week_number``) to gate.

    Returns:
        Tuple of (rewritten workouts, Japanese adjustment notes). When
        ``overall_flag`` is False the input is passed through unchanged and the
        notes list is empty.
    """
    if not deviation.get("overall_flag"):
        return workouts, []

    result: list[PlannedWorkout] = []
    notes: list[str] = []

    for workout in workouts:
        original_type = workout.workout_type.value
        downgraded_type = DOWNGRADE_MAP.get(original_type)

        if workout.week_number <= weeks_to_check and downgraded_type is not None:
            result.append(
                workout.model_copy(
                    update={"workout_type": WorkoutType(downgraded_type)}
                )
            )
            notes.append(
                f"Week{workout.week_number} Day{workout.day_of_week} の"
                f"{original_type} を {downgraded_type} にダウングレード"
                "（readiness 低下: HRV が個人帯を下回る、または RHR 上昇）"
            )
        else:
            result.append(workout)

    return result, notes
