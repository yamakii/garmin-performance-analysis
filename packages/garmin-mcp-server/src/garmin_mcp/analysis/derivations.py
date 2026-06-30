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


def _format_pace_km(pace_s_per_km: float) -> str:
    """Format a pace in seconds/km as ``M:SS/km`` (e.g. 405 -> ``6:45/km``)."""
    return f"{format_pace(pace_s_per_km)}/km"


# Training types whose next-run target is anchored to vVO2max (interval family).
_INTERVAL_TRAINING_TYPES = {
    "interval",
    "vo2max",
    "vo2_max",
    "speed",
    "repetition",
}

# Training types whose next-run target is anchored to LT pace (tempo family).
_TEMPO_TRAINING_TYPES = {"tempo", "threshold", "lactate_threshold"}

# Training types treated as recovery (still HR-based, distinct recommended_type).
_RECOVERY_TRAINING_TYPES = {"recovery"}


def compute_next_run_target(
    training_type: str | None,
    planned_workout: dict | None,
    vo2_max: dict | None,
    lactate_threshold: dict | None,
    avg_hr: int | None,
    avg_pace_s_per_km: float | None,
) -> dict:
    """Deterministic numeric core of next_run_target (prose left to agent).

    The accuracy-sensitive float arithmetic and ``M:SS/km`` formatting are
    computed here so the agent only adds prose (``summary_ja`` /
    ``adjustment_tip``) and never recomputes pace from raw physiology (Issue
    #672). Behaviour by family:

    - interval / vo2max / speed / repetition (vVO2max-based):
      ``vVO2max_kmh = vo2_max["precise_value"] / 3.5``;
      ``pace = 3600 / (vVO2max_kmh * f)`` for ``f`` in ``[0.95, 1.00]`` ->
      ``target_pace_slow_formatted`` (95%) / ``target_pace_fast_formatted``
      (100%).
    - tempo / threshold (LT-pace-based):
      ``lt_pace_s = 1000 / lactate_threshold["speed_mps"]``;
      ``target = lt_pace_s - 3`` -> ``target_pace_formatted``, ``target_hr``.
    - easy / recovery / base (HR-based): ``target_hr_low`` / ``target_hr_high``
      from ``avg_hr`` (±5bpm); reference pace = ``avg_pace`` (±5s) ->
      ``reference_pace_*_formatted``.

    Missing source data for the relevant family returns
    ``{"insufficient_data": True, "recommended_type": ..., "summary_ja": ...}``.
    The returned dict always includes ``recommended_type``.
    """
    # planned_workout's workout_type (if any) takes precedence over the
    # activity's own training_type for deciding the next target family.
    effective_type = training_type
    if planned_workout is not None and planned_workout.get("workout_type"):
        effective_type = planned_workout.get("workout_type")

    if effective_type in _INTERVAL_TRAINING_TYPES:
        return _interval_target(effective_type, vo2_max)
    if effective_type in _TEMPO_TRAINING_TYPES:
        return _tempo_target(effective_type, lactate_threshold, avg_hr)
    return _easy_target(effective_type, avg_hr, avg_pace_s_per_km)


def _interval_target(training_type: str | None, vo2_max: dict | None) -> dict:
    recommended_type = "interval"
    precise_value = vo2_max.get("precise_value") if vo2_max else None
    if precise_value is None:
        return {
            "recommended_type": recommended_type,
            "insufficient_data": True,
            "summary_ja": (
                "VO2maxデータがないため、インターバルの目標ペースを算出できない。"
            ),
        }

    vvo2max_kmh = precise_value / 3.5
    # Faster end uses 100% vVO2max, slower end uses 95%.
    pace_fast_s = 3600 / (vvo2max_kmh * 1.00)
    pace_slow_s = 3600 / (vvo2max_kmh * 0.95)
    return {
        "recommended_type": recommended_type,
        "vvo2max_kmh": round(vvo2max_kmh, 1),
        "target_pace_fast_formatted": _format_pace_km(pace_fast_s),
        "target_pace_slow_formatted": _format_pace_km(pace_slow_s),
    }


def _tempo_target(
    training_type: str | None,
    lactate_threshold: dict | None,
    avg_hr: int | None,
) -> dict:
    recommended_type = "tempo"
    speed_mps = lactate_threshold.get("speed_mps") if lactate_threshold else None
    if not speed_mps:
        return {
            "recommended_type": recommended_type,
            "insufficient_data": True,
            "summary_ja": (
                "乳酸閾値データがないため、テンポ走の目標ペースを算出できない。"
            ),
        }

    lt_pace_s = 1000 / speed_mps
    target_pace_s = lt_pace_s - 3
    return {
        "recommended_type": recommended_type,
        "lt_pace_formatted": _format_pace_km(lt_pace_s),
        "target_pace_formatted": _format_pace_km(target_pace_s),
        "target_hr": avg_hr,
    }


def _easy_target(
    training_type: str | None,
    avg_hr: int | None,
    avg_pace_s_per_km: float | None,
) -> dict:
    recommended_type = (
        "recovery" if training_type in _RECOVERY_TRAINING_TYPES else "easy"
    )
    if avg_hr is None:
        return {
            "recommended_type": recommended_type,
            "insufficient_data": True,
            "summary_ja": ("平均心拍データがないため、次回の目標心拍を算出できない。"),
        }

    result: dict = {
        "recommended_type": recommended_type,
        "target_hr_low": avg_hr - 5,
        "target_hr_high": avg_hr + 5,
    }
    if avg_pace_s_per_km is not None:
        result["reference_pace_formatted"] = _format_pace_km(avg_pace_s_per_km)
        result["reference_pace_fast_formatted"] = _format_pace_km(avg_pace_s_per_km - 5)
        result["reference_pace_slow_formatted"] = _format_pace_km(avg_pace_s_per_km + 5)
    return result


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
