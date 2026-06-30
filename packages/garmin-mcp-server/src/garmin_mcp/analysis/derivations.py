"""Deterministic derivations for analysis sections (no I/O).

These pure helpers move accuracy-sensitive judgments out of the LLM. Achievement
comparisons (HR / pace within target range), Japanese workout labels, and the
formatted ``targets`` / ``actuals`` strings are computed here so the agent only
adds the prose ``evaluation`` field. Leaving range comparison or label lookup to
the LLM risks hallucinated "achieved" verdicts (Issue #671).
"""

# Fallback Japanese labels by workout_type when planned_workouts.description_ja
# is null. Mirrors the mapping the agent previously held inline (Issue #671).
WORKOUT_TYPE_DESCRIPTION_JA: dict[str, str] = {
    "easy": "イージーラン",
    "recovery": "リカバリーラン",
    "long_run": "ロングラン",
    "tempo": "テンポ走",
    "threshold": "閾値走",
    "interval": "インターバル",
    "repetition": "レペティション",
}


def format_pace(pace_s_per_km: float) -> str:
    """Format a pace in seconds/km as ``M:SS`` (e.g. 405 -> ``6:45``)."""
    total = int(round(pace_s_per_km))
    minutes = total // 60
    seconds = total % 60
    return f"{minutes}:{seconds:02d}"


def compute_plan_achievement(
    planned_workout: dict | None,
    actual_avg_hr: int | None,
    actual_avg_pace_s_per_km: float | None,
) -> dict | None:
    """Deterministic plan vs actual skeleton (no prose ``evaluation``).

    Returns None when ``planned_workout`` is None. Otherwise returns::

        {workout_type, description_ja, targets, actuals, hr_achieved, pace_achieved}

    - ``hr_achieved``  = target_hr_low <= actual_avg_hr <= target_hr_high
      (None when either HR target bound or the actual HR is null)
    - ``pace_achieved`` = target_pace_low <= actual_pace <= target_pace_high
      (None when either pace target bound or the actual pace is null)
    - ``description_ja`` = planned_workout["description_ja"]
      or WORKOUT_TYPE_DESCRIPTION_JA.get(workout_type, workout_type)
    - ``targets`` / ``actuals`` = formatted strings ("120-145bpm", "6:45/km")

    The agent adds the prose ``evaluation`` field on top of this skeleton.
    """
    if planned_workout is None:
        return None

    workout_type = planned_workout.get("workout_type")
    description_ja = planned_workout.get("description_ja") or (
        WORKOUT_TYPE_DESCRIPTION_JA.get(workout_type, workout_type)
        if workout_type is not None
        else None
    )

    target_hr_low = planned_workout.get("target_hr_low")
    target_hr_high = planned_workout.get("target_hr_high")
    target_pace_low = planned_workout.get("target_pace_low")
    target_pace_high = planned_workout.get("target_pace_high")

    targets: dict[str, str] = {}
    if target_hr_low is not None and target_hr_high is not None:
        targets["hr"] = f"{target_hr_low}-{target_hr_high}bpm"
    if target_pace_low is not None and target_pace_high is not None:
        targets["pace"] = (
            f"{format_pace(target_pace_low)}-{format_pace(target_pace_high)}/km"
        )

    actuals: dict[str, str] = {}
    if actual_avg_hr is not None:
        actuals["hr"] = f"{actual_avg_hr}bpm"
    if actual_avg_pace_s_per_km is not None:
        actuals["pace"] = f"{format_pace(actual_avg_pace_s_per_km)}/km"

    hr_achieved: bool | None = None
    if (
        target_hr_low is not None
        and target_hr_high is not None
        and actual_avg_hr is not None
    ):
        hr_achieved = target_hr_low <= actual_avg_hr <= target_hr_high

    pace_achieved: bool | None = None
    if (
        target_pace_low is not None
        and target_pace_high is not None
        and actual_avg_pace_s_per_km is not None
    ):
        pace_achieved = target_pace_low <= actual_avg_pace_s_per_km <= target_pace_high

    return {
        "workout_type": workout_type,
        "description_ja": description_ja,
        "targets": targets,
        "actuals": actuals,
        "hr_achieved": hr_achieved,
        "pace_achieved": pace_achieved,
    }
