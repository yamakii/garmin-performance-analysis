"""Pre-fetch a shared weekly-review CONTEXT bundle for the /weekly-review skill.

The weekly review weighs a *target week W* (the plan week ahead) against the
prior completed week W-1's actuals, multi-week load, recovery, strength, hiking,
the Garmin plan, athlete goals and the last review — then the main session's single
coach judgement fuses it all into one prescription. That coach judgement is *not*
fanned out (the review's value is holistic reconciliation, not parallel section
work), so this script only consolidates the ~15 read MCP calls the skill made in
Steps 2-4 into one Python round-trip. ``catch_up_ingest`` (a write / side effect)
is intentionally left as a separate skill step and is NOT collected here.

Usage:
    uv run python -m garmin_mcp.scripts.prefetch_weekly_review_context --target this

Output (JSON to stdout, one line):
    {
      "week_start_date": "2026-07-06",
      "week_end_date": "2026-07-12",
      "prev_start": "2026-06-29",
      "prev_end": "2026-07-05",
      "week_in_progress": true,
      "week_start_day": 0,
      "as_of": "2026-07-10",
      "activity_ids": {"prev_week": [...], "current_week": [...]},
      "activities": [
        {"activity_id", "activity_date", "activity_name", "distance_km",
         "duration_seconds", "performance_trends": {...}|null, "weather": {...}|null}
      ],
      "fitness_summary": {...}|null,      # includes Garmin native hr_zones
      "load_trend": {...}|null,           # + long_run: {weekly_longest_sec,
                                          #   long_run_build_weeks,
                                          #   cutback_due_long_run} over the
                                          #   weeks completed before W, plus
                                          #   gate: the progression verdict for
                                          #   W-1's longest run (null when none
                                          #   reached _LONG_RUN_GATE_MIN_KM)
      "acwr": {...}|null,
      "recovery": {"trend": {...}|null,   # trend.series trimmed to the last
                                          #   _RECOVERY_SERIES_KEEP_DAYS days
                                          #   (aggregates stay 8-week)
                   "status": {...}|null,
                   "baseline_deviation": {...}|null},
      "strength": {"prev_week": [...]|null, "current_week": [...]|null},
      "hiking": {"prev_week": [...]|null, "current_week": [...]|null},
      "training_block": {                  # review backbone (Issue #980)
        "block": {...}|null,              #   the block covering W (mesocycle ledger)
        "ladder_step": {"current": step|null, "previous": ..., "next": ...},
        "weeks_to_block_end": int|null,   #   whole weeks from W to the block's end
        "weight_mode": str|null,
        "quality_sessions_per_week": int|null,
        "quality_types": [...]
      },
      "prescriptions_prev_week": {        # W-1 rows + deterministic adherence
        "rows": [...],
        "adherence": {"prescribed": n, "done": n, "replaced": n,
                      "skipped": n, "pending": n}
      },
      "scheduled_workouts": {...}|null,   # network (Garmin Connect); _safe/null-on-error
      "garmin_conflicts": [               # Garmin items contradicting the block
        {"date": "...", "garmin_title": "Tempo", "reason": "..."}
      ],
      "athlete_profile": {...}|null,      # without "goals" (see below)
      "goals_with_weeks_to_race": [{...goal, "weeks_to_race": int|null}],
      "past_review": {...}|null           # review_data without this_week /
                                          #   garmin_next_week (replayed keys)
    }

Three redundant slices are trimmed before returning (~18% smaller bundle,
Issue #933): goals ship only in ``goals_with_weeks_to_race``, the recovery
series keeps just its recent tail, and the past review drops the keys this
bundle already carries fresher. See ``_slim_*`` below.

Every reader is wrapped in ``_safe`` so a single failing collector yields
``null`` for its key rather than aborting the whole bundle (additive keys, like
prefetch_activity_context / prefetch_trend_context, Issue #235). On a fatal
target-resolution error the bundle is ``{"error": "..."}`` and the CLI exits 1.

Week boundaries reuse ``garmin_mcp.utils.week`` (configurable start day, Monday
fallback). The W-selection smart default (today == last day -> next week, else
this week), the previous-week bounds and ``weeks_to_race`` are derived here.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any

from garmin_mcp.analysis.derivations import (
    LONG_RUN_CUTBACK_TRIGGER_WEEKS,
    count_long_run_build_weeks,
    detect_garmin_conflicts,
    summarize_adherence,
)
from garmin_mcp.analysis.progression_gate import build_long_run_progression_gate
from garmin_mcp.database.connection import get_connection, get_db_path
from garmin_mcp.utils.week import get_week_start_day, week_bounds

# Multi-week load lookback (matches the skill's get_load_trend(lookback_weeks=10)).
_LOAD_LOOKBACK_WEEKS = 10
# Recovery-trend window in weeks (matches the skill's get_recovery_trend(weeks=8)).
_RECOVERY_TREND_WEEKS = 8
# Fitness summary lookback (the skill uses lookback_weeks=1 for a one-week view).
_FITNESS_LOOKBACK_WEEKS = 1
# Daily RHR/HRV rows kept in ``recovery.trend.series``. The review reads the
# aggregates (medians / rhr_trend / hrv_below_baseline_days / under_recovery),
# which the reader still derives over the full 8-week window; the raw series is
# only needed for a recent "HRV below baseline 2 nights running" spot check, so
# the full 57-day series is trimmed to its tail (Issue #933).
_RECOVERY_SERIES_KEEP_DAYS = 14
# ``past_review.review_data`` keys that replay the *previous* review's snapshot
# of the actuals and the Garmin plan. This bundle carries fresher equivalents
# (``activities`` / ``scheduled_workouts``), and the review only needs the past
# record for continuity of its judgements, so these are dropped (Issue #933).
_PAST_REVIEW_REPLAY_KEYS = ("this_week", "garmin_next_week")
# Minimum distance for W-1's longest run to be gated for progression (Issue
# #982). Matches the long-run definition used by the durability reader.
_LONG_RUN_GATE_MIN_KM = 10.0


def _safe[T](fn: Callable[[], T]) -> T | None:
    """Call ``fn`` and return its result, or ``None`` on any exception.

    Keeps a single failing collector from aborting the whole bundle
    (per-reader null-on-error; additive keys, Issue #235).
    """
    try:
        return fn()
    except Exception:
        return None


def _resolve_target_week(
    target: str | None, today: date, week_start_day: int
) -> tuple[date, date, date, date, bool]:
    """Resolve the review's target week W (and prior week W-1) bounds.

    Args:
        target: ``None`` (smart default), ``"this"``, ``"next"`` or an explicit
            ``YYYY-MM-DD`` date within the desired week.
        today: The reference "today" (test-injectable).
        week_start_day: Weekday the week begins on (0=Monday … 6=Sunday).

    Returns:
        ``(week_start, week_end, prev_start, prev_end, week_in_progress)`` where
        ``week_in_progress`` is whether ``today`` falls inside W.

    Raises:
        ValueError: If ``target`` is neither None/``"this"``/``"next"`` nor a
            parseable ``YYYY-MM-DD`` date.
    """
    this_start, this_end = week_bounds(today, week_start_day)

    if target is None:
        # Smart default: on the last day of the week, plan the next week;
        # otherwise review the week we are currently in.
        week_start = this_start + timedelta(days=7) if today == this_end else this_start
    elif target == "this":
        week_start = this_start
    elif target == "next":
        week_start = this_start + timedelta(days=7)
    else:
        try:
            d = datetime.strptime(target, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"invalid target '{target}': expected None|'this'|'next'|YYYY-MM-DD"
            ) from exc
        week_start, _ = week_bounds(d, week_start_day)

    week_end = week_start + timedelta(days=6)
    prev_start = week_start - timedelta(days=7)
    prev_end = week_start - timedelta(days=1)
    week_in_progress = week_start <= today <= week_end
    return week_start, week_end, prev_start, prev_end, week_in_progress


def _weeks_to_race(race_date: str | None, week_start: date) -> int | None:
    """Whole weeks from ``week_start`` to ``race_date`` (ceiling), or None.

    Returns ``None`` when ``race_date`` is missing or unparseable (an
    unconfirmed race date, e.g. a target marathon whose date is not yet set).
    """
    if race_date is None:
        return None
    try:
        rd = datetime.strptime(str(race_date), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return math.ceil((rd - week_start).days / 7)


def _long_run_gate(load_trend: dict[str, Any], week_start_date: str) -> dict[str, Any]:
    """Compute the long-run cutback gate over the weeks **completed** before W.

    The cutback cycle's **primary** gate is the long-run extension streak, not
    weekly volume (Issue #927): the long run is extended even in light weeks, so
    a volume streak resets there and under-counts the accumulated stress. This
    is computed here (deterministically) rather than left to the reviewing LLM.

    Only buckets starting strictly **before** ``week_start_date`` are counted:
    the gate asks "how many consecutive weeks did the long run grow *entering*
    W", so W's own bucket must be excluded. ``get_load_trend`` ends at today, so
    when the review runs mid-week that newest bucket is a partial week whose
    ``longest_run_sec`` is still ``None`` for anyone who runs long late in the
    week -- and a ``None`` reads as a no-run week, resetting the streak to 0
    (Issue #929). ``None``s inside the retained range are kept: a *completed*
    week with no run really is a reset boundary.

    Args:
        load_trend: A ``get_load_trend`` result; reads ``weeks[*].week_start``
            and ``weeks[*].longest_run_sec`` (oldest -> newest).
        week_start_date: Target week W's start (``YYYY-MM-DD``). Compared as an
            ISO string, which orders identically to the underlying dates.

    Returns:
        ``{"weekly_longest_sec": [int|None, ...], "long_run_build_weeks": int,
        "cutback_due_long_run": bool}`` where the flag is the streak reaching
        :data:`LONG_RUN_CUTBACK_TRIGGER_WEEKS`.
    """
    weeks = [
        w
        for w in (load_trend.get("weeks") or [])
        # A bucket with no week_start cannot be identified as W's own, so it is
        # kept (never silently dropped from the series).
        if str(w.get("week_start") or "") < week_start_date
    ]
    # Keep the Nones: a completed week with no run is a reset boundary.
    weekly_longest_sec = [w.get("longest_run_sec") for w in weeks]
    build_weeks = count_long_run_build_weeks(weekly_longest_sec)
    return {
        "weekly_longest_sec": weekly_longest_sec,
        "long_run_build_weeks": build_weeks,
        "cutback_due_long_run": build_weeks >= LONG_RUN_CUTBACK_TRIGGER_WEEKS,
    }


def _longest_long_run(activities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the longest activity of at least :data:`_LONG_RUN_GATE_MIN_KM`.

    Ties break on the later date then the higher id, so the pick is
    deterministic. ``None`` when the week held no long run.
    """
    long_runs = [
        a
        for a in activities
        if a.get("distance_km") is not None
        and float(a["distance_km"]) >= _LONG_RUN_GATE_MIN_KM
    ]
    if not long_runs:
        return None
    return max(
        long_runs,
        key=lambda a: (
            float(a["distance_km"]),
            str(a.get("activity_date") or ""),
            a["activity_id"],
        ),
    )


def _weeks_to_block_end(
    block: dict[str, Any] | None, week_start_date: str
) -> int | None:
    """Whole weeks from W's start to the end of the block covering it.

    ``0`` means W is the block's last week, ``2`` means two more weeks follow W.
    Returns ``None`` when there is no block or its ``end_date`` is missing /
    unparseable (a partially filled ledger must not break the bundle).
    """
    if not block:
        return None
    try:
        end = datetime.strptime(str(block.get("end_date")), "%Y-%m-%d").date()
        start = datetime.strptime(week_start_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (end - start).days // 7


def _collect_training_block(
    plan_reader: Any, week_start_date: str, user_id: str
) -> dict[str, Any]:
    """Collect the review's backbone: W's training block and its ladder step.

    Each reader call is individually ``_safe``, so a half-broken ledger degrades
    to ``None`` fields rather than nulling the whole key: the shape is always
    present and the skill can say "no block registered" instead of failing.

    Args:
        plan_reader: A ``PlanReader``.
        week_start_date: Target week W's start (``YYYY-MM-DD``).
        user_id: Ledger owner identifier.

    Returns:
        ``{"block", "ladder_step", "weeks_to_block_end", "weight_mode",
        "quality_sessions_per_week", "quality_types"}``. ``block`` is ``None``
        when no block covers W (nothing is registered, or W falls in a gap).
    """
    block = _safe(
        lambda: plan_reader.get_block_for_date(week_start_date, user_id=user_id)
    )
    ladder_step = _safe(
        lambda: plan_reader.get_ladder_step_for_week(week_start_date, user_id=user_id)
    ) or {"current": None, "previous": None, "next": None}

    return {
        "block": block,
        "ladder_step": ladder_step,
        "weeks_to_block_end": _weeks_to_block_end(block, week_start_date),
        "weight_mode": (block or {}).get("weight_mode"),
        "quality_sessions_per_week": (block or {}).get("quality_sessions_per_week"),
        "quality_types": (block or {}).get("quality_types") or [],
    }


def _collect_prev_week_prescriptions(
    plan_reader: Any, prev_start_date: str, user_id: str
) -> dict[str, Any]:
    """Collect W-1's prescriptions with their deterministic adherence summary.

    The rows carry the status ``reconcile_prescriptions`` wrote during ingest,
    so the review reads adherence rather than re-deriving it from activities.

    Args:
        plan_reader: A ``PlanReader``.
        prev_start_date: Previous week W-1's start (``YYYY-MM-DD``).
        user_id: Ledger owner identifier.

    Returns:
        ``{"rows": [...], "adherence": {...}}``; both empty / all-zero when W-1
        was never prescribed.
    """
    rows = (
        _safe(
            lambda: plan_reader.get_weekly_prescriptions(
                prev_start_date, user_id=user_id
            )
        )
        or []
    )
    return {"rows": rows, "adherence": summarize_adherence(rows)}


def _slim_athlete_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop the profile's ``goals`` copy (Issue #933).

    ``goals_with_weeks_to_race`` holds the same goal dicts plus the pre-computed
    ``weeks_to_race``, so ``athlete_profile.goals`` was a pure duplicate. The
    caller must derive ``goals_with_weeks_to_race`` from the *un-slimmed*
    profile first.

    Returns a copy; the reader's dict is never mutated. ``None`` passes through.
    """
    if profile is None:
        return None
    return {key: value for key, value in profile.items() if key != "goals"}


def _slim_recovery_trend(trend: dict[str, Any] | None) -> dict[str, Any] | None:
    """Trim ``series`` to its most recent :data:`_RECOVERY_SERIES_KEEP_DAYS` days.

    The aggregates already computed by the reader over the full window (medians,
    ``rhr_trend``, ``hrv_below_baseline_days``, ``under_recovery``) are kept
    as-is -- they are **not** recomputed from the shortened series.

    Returns a copy; the reader's dict is never mutated. A missing / non-list
    ``series`` (and ``None``) passes through unchanged.
    """
    if trend is None:
        return None
    series = trend.get("series")
    if not isinstance(series, list):
        return trend
    return {**trend, "series": series[-_RECOVERY_SERIES_KEEP_DAYS:]}


def _slim_past_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop :data:`_PAST_REVIEW_REPLAY_KEYS` from the past review's payload.

    The past review is carried for continuity with its previous judgements
    (``verdict`` / ``recommendations`` / ``overall`` / ``goal_alignment`` /
    ``periodization`` / ``recovery``), not to replay its stale snapshot of the
    actuals and the plan.

    Returns a copy; the reader's dict is never mutated. ``None`` and a
    non-dict ``review_data`` pass through unchanged.
    """
    if review is None:
        return None
    review_data = review.get("review_data")
    if not isinstance(review_data, dict):
        return review
    return {
        **review,
        "review_data": {
            key: value
            for key, value in review_data.items()
            if key not in _PAST_REVIEW_REPLAY_KEYS
        },
    }


def _resolve_activities(conn: Any, start: str, end: str) -> list[dict[str, Any]]:
    """Return activity metadata rows whose ``activity_date`` is within the window.

    Inclusive on both bounds, ordered chronologically (date then id) for
    deterministic output.
    """
    rows = conn.execute(
        """
        SELECT activity_id, activity_date, activity_name,
               total_distance_km, total_time_seconds
        FROM activities
        WHERE activity_date BETWEEN ? AND ?
        ORDER BY activity_date ASC, activity_id ASC
        """,
        [start, end],
    ).fetchall()
    return [
        {
            "activity_id": int(row[0]),
            "activity_date": str(row[1]),
            "activity_name": row[2],
            "distance_km": row[3],
            "duration_seconds": row[4],
        }
        for row in rows
    ]


def prefetch_weekly_review_context(
    target: str | None = None,
    today: str | None = None,
    user_id: str = "default",
) -> dict[str, Any]:
    """Fetch a single weekly-review CONTEXT bundle.

    Args:
        target: ``None`` (smart default), ``"this"``, ``"next"`` or a
            ``YYYY-MM-DD`` date within the desired target week W.
        today: Reference day (``YYYY-MM-DD``, test-injectable). Defaults to
            ``date.today()``.
        user_id: Athlete profile key (defaults to ``"default"``).

    Returns:
        A JSON-serializable bundle (see module docstring). ``{"error": "..."}``
        on a fatal error (unparseable ``today`` or ``target``).
    """
    try:
        today_d = (
            date.today()
            if today is None
            else datetime.strptime(today, "%Y-%m-%d").date()
        )
    except ValueError as exc:
        return {"error": f"invalid today '{today}': {exc}"}

    db_path = get_db_path()
    db_path_str = str(db_path)

    # Week-start day is per-athlete config (Monday fallback). Read it once.
    with get_connection(db_path) as conn:
        week_start_day = get_week_start_day(conn, user_id)

    try:
        (
            week_start,
            week_end,
            prev_start,
            prev_end,
            week_in_progress,
        ) = _resolve_target_week(target, today_d, week_start_day)
    except ValueError as exc:
        return {"error": str(exc)}

    week_start_s = str(week_start)
    week_end_s = str(week_end)
    prev_start_s = str(prev_start)
    prev_end_s = str(prev_end)

    # Single read txn: resolve both windows' activity metadata at once. The
    # current-week window is the target week itself; a future (next) week simply
    # has no rows, and a week-in-progress naturally yields the actuals so far.
    with get_connection(db_path) as conn:
        prev_activities = _resolve_activities(conn, prev_start_s, prev_end_s)
        current_activities = _resolve_activities(conn, week_start_s, week_end_s)

    prev_ids = [a["activity_id"] for a in prev_activities]
    current_ids = [a["activity_id"] for a in current_activities]

    # Union of both windows, de-duplicated on activity_id (prev first, then any
    # current-week-only ids), enriched per-activity with trends + weather.
    merged: dict[int, dict[str, Any]] = {}
    for a in [*prev_activities, *current_activities]:
        merged.setdefault(a["activity_id"], a)

    from garmin_mcp.database.db_reader import GarminDBReader

    reader = GarminDBReader(db_path_str)

    activities: list[dict[str, Any]] = []
    for a in merged.values():
        aid = a["activity_id"]
        activities.append(
            {
                **a,
                "performance_trends": _safe(
                    partial(reader.get_performance_trends, aid)
                ),
                "weather": _safe(partial(reader.get_weather_data, aid)),
            }
        )

    # Fitness summary (VDOT + Garmin native hr_zones + weekly volume).
    def _fitness_summary() -> dict[str, Any]:
        from garmin_mcp.fitness.fitness_assessor import FitnessAssessor

        assessor = FitnessAssessor(db_path=db_path_str)
        return assessor.assess(lookback_weeks=_FITNESS_LOOKBACK_WEEKS).model_dump()

    fitness_summary = _safe(_fitness_summary)

    # Multi-week load + ACWR (cutback-cycle material).
    load_trend = _safe(
        lambda: reader.get_load_trend(_LOAD_LOOKBACK_WEEKS, end_date=str(today_d))
    )
    # Primary cutback gate: the long-run extension streak (Issue #927). Folded
    # into the bundle deterministically so the review never re-derives it. Only
    # the weeks completed before W count, so W's own in-progress bucket cannot
    # zero the streak (Issue #929).
    if isinstance(load_trend, dict):
        load_trend["long_run"] = _long_run_gate(load_trend, week_start_s)
        # Secondary gate (Issue #982): did W-1's long run hold the legs
        # together? The review reads the same deterministic verdict the
        # activity summary shows, instead of eyeballing the fade itself.
        reference_run = _longest_long_run(prev_activities)
        load_trend["long_run"]["gate"] = (
            _safe(
                partial(
                    build_long_run_progression_gate,
                    reader,
                    reference_run["activity_id"],
                )
            )
            if reference_run is not None
            else None
        )
    acwr = _safe(lambda: reader.get_acwr(end_date=str(today_d)))

    # Recovery: RHR/HRV trend, morning go/no-go status, personal-baseline z.
    recovery = {
        "trend": _safe(lambda: reader.get_recovery_trend(_RECOVERY_TREND_WEEKS)),
        "status": _safe(lambda: reader.get_recovery_status()),
        "baseline_deviation": _safe(lambda: reader.get_wellness_baseline_deviation()),
    }

    # Strength sessions for both windows (DB only, no Garmin access).
    strength = {
        "prev_week": _safe(
            lambda: reader.get_strength_sessions(prev_start_s, prev_end_s)
        ),
        "current_week": _safe(
            lambda: reader.get_strength_sessions(week_start_s, week_end_s)
        ),
    }

    # Hiking sessions for both windows (DB only, no Garmin access). Hikes live
    # outside ``activities``, so the review only sees them through this key.
    hiking = {
        "prev_week": _safe(
            lambda: reader.get_hiking_sessions(prev_start_s, prev_end_s)
        ),
        "current_week": _safe(
            lambda: reader.get_hiking_sessions(week_start_s, week_end_s)
        ),
    }

    # Garmin plan for W (network / Garmin Connect). _safe so a live-HTTP failure
    # nulls this key; the skill keeps a direct-MCP fallback for that case.
    def _scheduled_workouts() -> dict[str, Any]:
        from garmin_mcp.fitness.garmin_calendar import GarminCalendarReader

        calendar_reader = GarminCalendarReader()
        workouts = calendar_reader.get_scheduled_workouts(week_start_s, week_end_s)
        return {
            "start_date": week_start_s,
            "end_date": week_end_s,
            "count": len(workouts),
            "workouts": workouts,
        }

    scheduled_workouts = _safe(_scheduled_workouts)

    # Review backbone (Issue #980): the stored mesocycle block + ladder step for
    # W, and how W-1's prescriptions were actually followed. The Garmin plan is
    # demoted to a conflict signal derived from the block below.
    from garmin_mcp.database.readers.plan import PlanReader

    plan_reader = PlanReader(db_path=db_path_str)
    training_block = _collect_training_block(plan_reader, week_start_s, user_id)
    prescriptions_prev_week = _collect_prev_week_prescriptions(
        plan_reader, prev_start_s, user_id
    )

    # Garmin calendar items that contradict W's block (deterministic; empty list
    # rather than null so the skill can treat "no conflicts" and "no plan" alike).
    garmin_conflicts = (
        _safe(
            lambda: detect_garmin_conflicts(
                (scheduled_workouts or {}).get("workouts") or [],
                training_block["ladder_step"],
                training_block["quality_sessions_per_week"],
                (training_block["block"] or {}).get("phase"),
                week_start_s,
                week_start_day,
            )
        )
        or []
    )

    # Athlete profile (goals / focus) + last review, via AthleteReader.
    from garmin_mcp.database.readers.athlete import AthleteReader

    athlete_reader = AthleteReader(db_path=db_path_str)
    athlete_profile = _safe(lambda: athlete_reader.get_athlete_profile(user_id))
    past_review = _safe(lambda: athlete_reader.get_weekly_review(user_id=user_id))

    # Goals with weeks-to-race pre-computed against W's start (ceil, null-safe).
    # Derived *before* the profile is slimmed: this list is the only copy of the
    # goals that ships in the bundle.
    goals = (athlete_profile or {}).get("goals") or []
    goals_with_weeks_to_race = [
        {**goal, "weeks_to_race": _weeks_to_race(goal.get("race_date"), week_start)}
        for goal in goals
    ]

    # Trim the redundant slices (Issue #933). Copies only -- reader results are
    # never mutated.
    athlete_profile = _slim_athlete_profile(athlete_profile)
    recovery["trend"] = _slim_recovery_trend(recovery["trend"])
    past_review = _slim_past_review(past_review)

    return {
        "week_start_date": week_start_s,
        "week_end_date": week_end_s,
        "prev_start": prev_start_s,
        "prev_end": prev_end_s,
        "week_in_progress": week_in_progress,
        "week_start_day": week_start_day,
        "as_of": str(today_d),
        "activity_ids": {"prev_week": prev_ids, "current_week": current_ids},
        "activities": activities,
        "fitness_summary": fitness_summary,
        "load_trend": load_trend,
        "acwr": acwr,
        "recovery": recovery,
        "strength": strength,
        "hiking": hiking,
        "training_block": training_block,
        "prescriptions_prev_week": prescriptions_prev_week,
        "scheduled_workouts": scheduled_workouts,
        "garmin_conflicts": garmin_conflicts,
        "athlete_profile": athlete_profile,
        "goals_with_weeks_to_race": goals_with_weeks_to_race,
        "past_review": past_review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-fetch a shared weekly-review CONTEXT bundle."
    )
    parser.add_argument(
        "--target",
        default=None,
        help="None (smart default) | 'this' | 'next' | YYYY-MM-DD (a day in W).",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Reference day YYYY-MM-DD (default: today). For testing.",
    )
    parser.add_argument("--user-id", default="default", help="Athlete profile key.")
    args = parser.parse_args()

    result = prefetch_weekly_review_context(args.target, args.today, args.user_id)
    print(json.dumps(result, ensure_ascii=False, default=str))

    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
