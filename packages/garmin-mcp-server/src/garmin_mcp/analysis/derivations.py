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


def compute_weighted_star_rating(
    axis_scores: dict[str, float], weights: dict[str, float]
) -> float:
    """Recompute a weighted star rating from per-axis scores (Issue #706).

    ``rating = sum(axis_scores[k] * weights[k]) / sum(weights.values())``,
    clamped to [0.0, 5.0] and returned as ``round(rating, 1)``. This is the
    deterministic core behind the summary 4-axis rating and the phase /
    environment weighted ratings, so the merge guard can verify the LLM's
    stated ``star_rating`` instead of trusting its arithmetic.

    Raises:
        ValueError: When ``weights`` keys do not exactly match ``axis_scores``
            keys, when either dict is empty, or when the weights sum to <= 0.
    """
    if not axis_scores or not weights:
        raise ValueError("axis_scores and weights must be non-empty")
    if set(axis_scores) != set(weights):
        raise ValueError(
            "weights keys must match axis_scores keys: "
            f"axis_scores={sorted(axis_scores)}, weights={sorted(weights)}"
        )
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError(f"weights must sum to a positive value, got {total_weight}")

    rating = sum(axis_scores[key] * weights[key] for key in axis_scores) / total_weight
    clamped = min(5.0, max(0.0, rating))
    return round(clamped, 1)


# --- training_type -> category mapping for phase / environment (Issue #673) ---
# These move the classification tables out of the agent prose
# (unified-section-analyst.md) so the phase / environment sections select
# evaluation criteria deterministically. Category keys mirror the validation
# contracts (validation/contracts.py):
#   phase:       low_moderate | tempo_threshold | interval_sprint
#   environment: recovery | base_moderate | tempo_threshold | interval_sprint

# planned_workout.workout_type -> phase category (takes precedence over the
# activity's own training_type). Ports unified-section-analyst.md L179-184.
_PHASE_WORKOUT_TYPE_CATEGORY: dict[str, str] = {
    "easy_run": "low_moderate",
    "recovery_run": "low_moderate",
    "tempo_run": "tempo_threshold",
    "threshold_run": "tempo_threshold",
    "interval": "interval_sprint",
    "speed_work": "interval_sprint",
    "vo2max_intervals": "interval_sprint",
    "long_run": "low_moderate",  # may be reclassified when target_hr_high is high
}

# activity training_type -> phase category (fallback when no planned_workout).
# Ports unified-section-analyst.md L186-189.
_PHASE_TRAINING_TYPE_CATEGORY: dict[str, str] = {
    "recovery": "low_moderate",
    "aerobic_base": "low_moderate",
    "tempo": "tempo_threshold",
    "lactate_threshold": "tempo_threshold",
    "vo2max": "interval_sprint",
    "anaerobic_capacity": "interval_sprint",
    "speed": "interval_sprint",
    "interval_training": "interval_sprint",
}

# A planned long_run whose target_hr_high reaches tempo intensity is evaluated
# as tempo_threshold (unified-section-analyst.md L185). The agent spec gives no
# explicit number; 160bpm marks the lower edge of tempo/threshold HR.
_LONG_RUN_TEMPO_HR_THRESHOLD = 160


def map_phase_category(training_type: str | None, planned_workout: dict | None) -> str:
    """Map training_type / planned_workout to a phase evaluation category.

    Ports the unified-section-analyst.md L179-191 decision table so the phase
    section selects evaluation criteria deterministically instead of relying on
    the LLM. ``planned_workout.workout_type`` takes precedence over the
    activity's own ``training_type``.

    Returns one of ``'low_moderate'`` | ``'tempo_threshold'`` |
    ``'interval_sprint'`` (default ``'tempo_threshold'`` when neither source
    resolves a category).
    """
    if planned_workout is not None:
        workout_type = planned_workout.get("workout_type")
        if workout_type == "long_run":
            target_hr_high = planned_workout.get("target_hr_high")
            if (
                target_hr_high is not None
                and target_hr_high >= _LONG_RUN_TEMPO_HR_THRESHOLD
            ):
                return "tempo_threshold"
            return "low_moderate"
        category = (
            _PHASE_WORKOUT_TYPE_CATEGORY.get(workout_type) if workout_type else None
        )
        if category is not None:
            return category

    category = (
        _PHASE_TRAINING_TYPE_CATEGORY.get(training_type) if training_type else None
    )
    if category is not None:
        return category
    return "tempo_threshold"


def map_environment_category(training_type: str | None) -> str:
    """Map training_type to an environment evaluation category.

    Ports unified-section-analyst.md L246-250 so the environment section selects
    ``temperature_by_training_type`` criteria deterministically. Returns one of
    ``'recovery'`` | ``'base_moderate'`` | ``'tempo_threshold'`` |
    ``'interval_sprint'`` (default ``'base_moderate'`` when ``training_type`` is
    null or unrecognized).
    """
    if training_type is None:
        return "base_moderate"
    t = training_type.lower()
    if "recovery" in t:
        return "recovery"
    if "tempo" in t or "threshold" in t:
        return "tempo_threshold"
    if (
        "interval" in t
        or "sprint" in t
        or "vo2" in t
        or "speed" in t
        or "anaerobic" in t
    ):
        return "interval_sprint"
    # easy / base / moderate and any other aerobic type.
    return "base_moderate"
