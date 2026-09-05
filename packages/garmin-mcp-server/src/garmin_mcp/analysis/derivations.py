"""Deterministic derivations for analysis sections (no I/O).

These pure helpers move accuracy-sensitive judgments out of the LLM. Achievement
comparisons (HR / pace within target range), Japanese workout labels, and the
formatted ``targets`` / ``actuals`` strings are computed here so the agent only
adds the prose ``evaluation`` field. Leaving range comparison or label lookup to
the LLM risks hallucinated "achieved" verdicts (Issue #671).
"""

from datetime import date, datetime
from typing import Any

from garmin_mcp.utils.week import week_bounds

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
    hr_zones_detail: dict | None = None,
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
    - easy / recovery / base (HR-based, Issue #863): the target band is the
      athlete's **Garmin native HR zone** for the training-type family --
      recovery -> Zone1, easy/base -> Zone2 -- read from ``hr_zones_detail``.
      This preserves training-type intent and pins the ceiling to the real
      Zone2 upper (not the last run's ``avg_hr``). The run's own ``avg_hr`` is
      attached as ``typical_hr`` (personal observed center for prose). When
      native zones are unavailable the legacy ``avg_hr ± 5bpm`` band is used as
      a fallback. Reference pace = ``avg_pace`` (±5s) -> ``reference_pace_*``.

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
    return _easy_target(effective_type, avg_hr, avg_pace_s_per_km, hr_zones_detail)


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


def _zone_band(
    hr_zones_detail: dict | None, zone_number: int
) -> tuple[int, int] | None:
    """Return the ``(low, high)`` bpm bounds of a Garmin native HR zone.

    Reads ``hr_zones_detail`` (shape ``{"zones": [{"zone_number", "low_boundary",
    "high_boundary", ...}]}`` from ``heart_rate_zones``). Returns ``None`` when
    the detail is missing or the requested zone has no usable bounds, so callers
    can fall back to a legacy band.
    """
    if not hr_zones_detail:
        return None
    for zone in hr_zones_detail.get("zones", []):
        if zone.get("zone_number") == zone_number:
            low = zone.get("low_boundary")
            high = zone.get("high_boundary")
            if low is None or high is None:
                return None
            return int(low), int(high)
    return None


def _easy_target(
    training_type: str | None,
    avg_hr: int | None,
    avg_pace_s_per_km: float | None,
    hr_zones_detail: dict | None = None,
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

    # Training-type-anchored band from Garmin native zones (Issue #863):
    # recovery -> Zone1, easy/base -> Zone2. This preserves the training intent
    # and pins the ceiling to the real Zone2 upper instead of the last run's
    # avg_hr. Fall back to the legacy avg_hr +/- 5 band when zones are absent.
    target_zone_number = 1 if recommended_type == "recovery" else 2
    band = _zone_band(hr_zones_detail, target_zone_number)
    if band is not None:
        low, high = band
        result: dict = {
            "recommended_type": recommended_type,
            "target_hr_low": low,
            "target_hr_high": high,
            "target_zone": f"Zone{target_zone_number}",
            "hr_basis": "garmin_native_zone",
            "typical_hr": avg_hr,
        }
    else:
        result = {
            "recommended_type": recommended_type,
            "target_hr_low": avg_hr - 5,
            "target_hr_high": avg_hr + 5,
            "hr_basis": "recent_avg_hr",
        }
    if avg_pace_s_per_km is not None:
        result["reference_pace_formatted"] = _format_pace_km(avg_pace_s_per_km)
        result["reference_pace_fast_formatted"] = _format_pace_km(avg_pace_s_per_km - 5)
        result["reference_pace_slow_formatted"] = _format_pace_km(avg_pace_s_per_km + 5)
    return result


def weighted_star_rating_raw(
    axis_scores: dict[str, float], weights: dict[str, float]
) -> float:
    """Weighted star rating as the unrounded, clamped weighted mean (Issue #859).

    ``rating = sum(axis_scores[k] * weights[k]) / sum(weights.values())``,
    clamped to [0.0, 5.0] with **no rounding**. This is the true weighted mean
    the merge guard compares against, so a ``X.X5`` boundary (where the LLM's
    half-up rounding and Python's round-half-to-even can legitimately disagree
    by one display notch) does not false-fail the consistency check.

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
    return min(5.0, max(0.0, rating))


def compute_weighted_star_rating(
    axis_scores: dict[str, float], weights: dict[str, float]
) -> float:
    """Recompute a weighted star rating from per-axis scores (Issue #706).

    ``round(weighted_star_rating_raw(axis_scores, weights), 1)``: the clamped
    weighted mean displayed to 1 decimal. This is the deterministic core behind
    the summary 4-axis rating and the phase / environment weighted ratings, so
    the merge guard can verify the LLM's stated ``star_rating`` instead of
    trusting its arithmetic.

    Raises:
        ValueError: When ``weights`` keys do not exactly match ``axis_scores``
            keys, when either dict is empty, or when the weights sum to <= 0.
    """
    return round(weighted_star_rating_raw(axis_scores, weights), 1)


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


# ---------------------------------------------------------------------------
# Trend derivations (Issue #790): deterministic layer for trend narration.
#
# These pure helpers compute the accuracy-sensitive judgments (period deltas,
# consecutive build streaks, cross-signal fusion flags) so the trend-narration
# LLM only writes prose. Fabricated "load is up 12%" / "you are overreaching"
# verdicts are avoided by computing them here (see #714 ADR §4).
# ---------------------------------------------------------------------------

# ACWR statuses that indicate an elevated acute load (see TrainingLoadReader).
_HIGH_LOAD_ACWR_STATUSES = {"caution", "high_risk"}
# The HRV recovery state string that flags accumulated under-recovery.
_UNDER_RECOVERY_HRV_STATE = "under_recovery"
# A period-over-period form delta (%) at or below this counts as a meaningful
# form decline for cross-signal fusion. Small wobble (e.g. +1.0 / -0.5) does
# not trip a fusion flag; only a sustained worsening does.
_FORM_DECLINE_PCT_THRESHOLD = -2.0


def compute_period_delta_pct(
    current: float | None, prior: float | None
) -> float | None:
    """Return the percentage change from ``prior`` to ``current``.

    ``(current - prior) / prior * 100``. Returns ``None`` when either operand is
    ``None`` or when ``prior == 0`` (undefined / division by zero). The result
    is rounded to 1 decimal place.
    """
    if current is None or prior is None:
        return None
    if prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)


def count_consecutive_build_weeks(weekly_loads: list[float]) -> int:
    """Count the trailing streak of week-over-week load increases.

    Walks backward from the last week while each prior week's load is strictly
    less than the following week's load (an increasing streak). The final week
    itself is always counted, so a list with no trailing increase returns ``1``.
    An empty list returns ``0``.

    Examples:
        ``[30, 32, 35, 40]`` -> ``4`` (all increasing)
        ``[40, 32, 35, 38]`` -> ``3`` (streak breaks at the 40 -> 32 drop)
        ``[50, 40, 30]``     -> ``1`` (immediate decrease)
        ``[]``               -> ``0``
    """
    if not weekly_loads:
        return 0
    count = 1
    for i in range(len(weekly_loads) - 1, 0, -1):
        if weekly_loads[i - 1] < weekly_loads[i]:
            count += 1
        else:
            break
    return count


# --- Long-run extension streak (Issue #927) --------------------------------
# The cutback cycle's primary gate is the *long run* (the week's longest on-feet
# time), not weekly volume. The athlete extends the long run even in light
# weeks, so a volume-based streak resets on those weeks and systematically
# under-counts the accumulated tendon / bone stress the long run drives.
#
# A week extends the streak at >= +3% over the previous week's longest run; a
# hold (75%-103%) neither extends nor resets it (the streak keeps walking back);
# a drop below 75% is a real cutback and ends the walk.
_LONG_RUN_EXT_RATIO = 1.03
_LONG_RUN_RESET_RATIO = 0.75

# Trailing long-run extension streak at which a cutback becomes due (primary
# gate; the weekly-volume / ACWR gates stay as secondary OR conditions).
LONG_RUN_CUTBACK_TRIGGER_WEEKS = 3


def count_long_run_build_weeks(weekly_longest_sec: list[float | None]) -> int:
    """Trailing streak of >=+3% weekly longest-run extensions.

    Walks backward from the last week: ``ratio >= 1.03`` -> +1; ratio in
    ``[0.75, 1.03)`` -> skip (a hold preserves the streak without extending it);
    ``ratio < 0.75`` or a ``None`` / missing week -> stop (reset boundary; a
    week with no run counts as a reset). ``[]`` or a single week -> ``0``.

    Args:
        weekly_longest_sec: Weekly longest-run durations in seconds, oldest ->
            newest. ``None`` marks a week with no run.

    Examples:
        ``[3250, 7819, 8125, 8562]``  -> ``3`` (three straight extensions)
        ``[7200, 7500, 7480, 7800]``  -> ``2`` (7480 is a hold, not a reset)
        ``[8000, 3000, 7000]``        -> ``1`` (0.375 ratio ends the walk)
    """
    count = 0
    for i in range(len(weekly_longest_sec) - 1, 0, -1):
        current = weekly_longest_sec[i]
        prior = weekly_longest_sec[i - 1]
        if current is None or prior is None or prior <= 0:
            break
        ratio = current / prior
        if ratio >= _LONG_RUN_EXT_RATIO:
            count += 1
        elif ratio < _LONG_RUN_RESET_RATIO:
            break
        # else: a hold -- neither extends nor resets; keep walking back.
    return count


def compute_fusion_flags(
    acwr_status: str | None,
    hrv_state: str | None,
    form_delta_pct: float | None,
) -> dict[str, bool]:
    """Fuse load / recovery / form signals into cross-signal warning flags.

    Every returned value is always a ``bool`` (never ``None``), so the flags are
    safe to read directly. All flags are *warning* flags: they stay ``False``
    when signals are healthy, so an optimal/balanced/improving snapshot yields
    all ``False``.

    Flags:
        - ``high_load_low_recovery``: ``acwr_status`` is caution/high_risk **and**
          ``hrv_state == "under_recovery"`` (classic overreaching pattern).
        - ``high_load_form_decline``: elevated load **and** a form decline
          (``form_delta_pct <= _FORM_DECLINE_PCT_THRESHOLD``).
        - ``under_recovery_form_decline``: HRV under-recovery **and** a form
          decline.
    """
    high_load = acwr_status in _HIGH_LOAD_ACWR_STATUSES
    under_recovery = hrv_state == _UNDER_RECOVERY_HRV_STATE
    form_declining = (
        form_delta_pct is not None and form_delta_pct <= _FORM_DECLINE_PCT_THRESHOLD
    )

    return {
        "high_load_low_recovery": high_load and under_recovery,
        "high_load_form_decline": high_load and form_declining,
        "under_recovery_form_decline": under_recovery and form_declining,
    }


def compute_trend_headline_metrics(context: dict[str, Any]) -> dict[str, Any]:
    """Extract deterministic headline metrics from a trend CONTEXT bundle.

    The trend-narration analog of :func:`compute_plan_achievement`: it folds the
    prefetched trend readers into the display-ready numbers so the LLM only adds
    prose. Missing inputs are filled with ``None`` (never raises on a partial or
    empty ``context``).

    Args:
        context: A trend CONTEXT bundle. Reads ``load_trend.weeks[*].load_km``
            (weekly loads, oldest -> newest),
            ``load_trend.weeks[*].longest_run_sec``, ``acwr.status``,
            ``recovery_trend.hrv`` and ``form_delta_pct`` when present.

    Returns:
        Dict with the always-present keys:
        - ``load_delta_pct``: percentage change of the last week's load vs the
          prior week (``None`` when fewer than two weekly loads exist).
        - ``build_weeks``: trailing week-over-week build streak (``None`` when no
          weekly loads exist).
        - ``long_run_build_weeks``: trailing streak of >=+3% longest-run
          extensions (:func:`count_long_run_build_weeks`; ``0`` when absent).
        - ``fusion_flags``: :func:`compute_fusion_flags` output (always a dict).
    """
    load_trend = context.get("load_trend") or {}
    weeks = load_trend.get("weeks") or []
    loads = [w.get("load_km") for w in weeks if w.get("load_km") is not None]
    # Keep the Nones: a week with no run is a reset boundary for the streak.
    weekly_longest_sec = [w.get("longest_run_sec") for w in weeks]

    load_delta_pct: float | None = None
    build_weeks: int | None = None
    if len(loads) >= 2:
        load_delta_pct = compute_period_delta_pct(loads[-1], loads[-2])
    if loads:
        build_weeks = count_consecutive_build_weeks(loads)

    acwr = context.get("acwr") or {}
    acwr_status = acwr.get("status")

    hrv = (context.get("recovery_trend") or {}).get("hrv") or {}
    # Map the recovery bundle to the string the pure fusion helper expects:
    # the under-recovery boolean takes precedence over the raw HRV status.
    hrv_state = (
        _UNDER_RECOVERY_HRV_STATE if hrv.get("under_recovery") else hrv.get("status")
    )

    form_delta_pct = context.get("form_delta_pct")

    return {
        "load_delta_pct": load_delta_pct,
        "build_weeks": build_weeks,
        "long_run_build_weeks": count_long_run_build_weeks(weekly_longest_sec),
        "fusion_flags": compute_fusion_flags(acwr_status, hrv_state, form_delta_pct),
    }


# ---------------------------------------------------------------------------
# Weekly-review plan backbone (Issue #980)
# ---------------------------------------------------------------------------
# The review's backbone is the stored mesocycle (training block + long-run
# ladder step), not the Garmin adaptive plan. Garmin's calendar is demoted to a
# *conflict* signal: it is only worth mentioning where it contradicts the block.
# Deciding "does this Garmin item conflict?" and "how well was last week's
# prescription followed?" is pure bookkeeping, so both are computed here rather
# than left to the reviewing LLM (see #714 ADR §4).

#: Lowercased title tokens that mark a Garmin calendar item as a quality (hard)
#: session. Matched as substrings, so "Tempo Run" / "VO2 Max" both hit.
QUALITY_TITLE_TOKENS: tuple[str, ...] = (
    "tempo",
    "threshold",
    "anaerobic",
    "sprint",
    "vo2",
    "speed",
    "interval",
)

#: Block phases in which *any* quality session conflicts with the plan.
_NO_QUALITY_PHASES = frozenset({"cutback", "recovery", "taper"})

#: Days around the long-run day within which a quality session conflicts with
#: it (1 = the day before / the day after also collide).
_LONG_RUN_ADJACENCY_DAYS = 1

#: Prescription statuses that are still open (the session has not been resolved
#: against an actual run yet).
_PENDING_PRESCRIPTION_STATUSES = frozenset({"prescribed", "registered"})

#: Prescription statuses reconciliation resolves a row into.
_RESOLVED_PRESCRIPTION_STATUSES = ("done", "replaced", "skipped")


def is_quality_title(title: str | None) -> bool:
    """Return whether a Garmin calendar title names a quality (hard) session.

    Matching is case-insensitive substring matching against
    :data:`QUALITY_TITLE_TOKENS`; a missing title is never quality.
    """
    if not title:
        return False
    lowered = str(title).lower()
    return any(token in lowered for token in QUALITY_TITLE_TOKENS)


def detect_garmin_conflicts(
    scheduled_workouts: list[dict[str, Any]],
    ladder_step: dict[str, Any] | None,
    quality_sessions_per_week: int | None,
    block_phase: str | None,
    week_start_date: str,
    week_start_day: int = 0,
) -> list[dict[str, Any]]:
    """List the Garmin calendar items that contradict the week's training block.

    Only *quality* items (:func:`is_quality_title`) inside the target week can
    conflict; easy / base / rest items are ignored entirely. Each conflicting
    item yields exactly one row, using the first rule that matches:

    1. ``quality_in_cutback_week`` — the block's ``phase`` is cutback / recovery
       / taper, where any quality session is off-plan.
    2. ``quality_on_long_day`` — the item lands on the long-run day (the last
       day of the week) or the day before / after, colliding with the ladder
       step. Only applied when the week actually has a ladder step
       (``ladder_step["current"]``); without one there is no known long run to
       collide with.
    3. ``second_quality_session`` — the item exceeds the block's
       ``quality_sessions_per_week`` budget. Items are counted in date order, so
       the *extra* ones (index >= the budget) are flagged, not the first.

    Args:
        scheduled_workouts: ``GarminCalendarReader.get_scheduled_workouts`` rows
            (``{date, title, ...}``). Items outside the week, without a date or
            with an unparseable date are skipped.
        ladder_step: ``{"current", "previous", "next"}`` from
            ``PlanReader.get_ladder_step_for_week``, or ``None``.
        quality_sessions_per_week: The block's quality budget. ``None`` disables
            rule 3 (no budget declared).
        block_phase: The block's ``phase``, or ``None``.
        week_start_date: The target week's start (``YYYY-MM-DD``).
        week_start_day: Weekday the week begins on (0=Monday … 6=Sunday), used
            to derive the week's inclusive bounds.

    Returns:
        ``[{"date", "garmin_title", "reason"}, ...]`` in date order. Empty when
        nothing conflicts (the common case for an all-base week).

    Raises:
        ValueError: If ``week_start_date`` is not a ``YYYY-MM-DD`` date.
    """
    week_start, week_end = week_bounds(
        datetime.strptime(week_start_date, "%Y-%m-%d").date(), week_start_day
    )

    quality_items: list[tuple[date, dict[str, Any]]] = []
    for item in scheduled_workouts or []:
        if not is_quality_title(item.get("title")):
            continue
        try:
            item_date = date.fromisoformat(str(item.get("date")))
        except (TypeError, ValueError):
            continue
        if not (week_start <= item_date <= week_end):
            continue
        quality_items.append((item_date, item))
    quality_items.sort(key=lambda pair: pair[0])

    # No ladder step -> the week has no known long run to collide with.
    long_run_day = week_end if (ladder_step or {}).get("current") else None
    no_quality_phase = str(block_phase or "").lower() in _NO_QUALITY_PHASES

    conflicts: list[dict[str, Any]] = []
    for index, (item_date, item) in enumerate(quality_items):
        if no_quality_phase:
            reason = "quality_in_cutback_week"
        elif (
            long_run_day is not None
            and abs((item_date - long_run_day).days) <= _LONG_RUN_ADJACENCY_DAYS
        ):
            reason = "quality_on_long_day"
        elif (
            quality_sessions_per_week is not None and index >= quality_sessions_per_week
        ):
            reason = "second_quality_session"
        else:
            continue
        conflicts.append(
            {
                "date": item_date.isoformat(),
                "garmin_title": item.get("title"),
                "reason": reason,
            }
        )
    return conflicts


def summarize_adherence(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count how a week's prescriptions ended up, for the review's adherence line.

    Args:
        rows: ``weekly_prescriptions`` rows (only ``status`` is read).

    Returns:
        ``{"prescribed": total, "done": n, "replaced": n, "skipped": n,
        "pending": n}`` where ``prescribed`` is the row count (how many sessions
        were prescribed) and ``pending`` counts everything reconciliation has
        not resolved yet (``prescribed`` / ``registered``, plus any unknown
        status, which is treated as unresolved rather than silently dropped).
    """
    summary = {
        "prescribed": len(rows or []),
        "done": 0,
        "replaced": 0,
        "skipped": 0,
        "pending": 0,
    }
    for row in rows or []:
        status = str(row.get("status") or "")
        if status in _RESOLVED_PRESCRIPTION_STATUSES:
            summary[status] += 1
        else:
            summary["pending"] += 1
    return summary
