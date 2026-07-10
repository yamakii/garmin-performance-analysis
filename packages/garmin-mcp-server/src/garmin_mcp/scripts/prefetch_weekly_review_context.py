"""Pre-fetch a shared weekly-review CONTEXT bundle for the /weekly-review skill.

The weekly review weighs a *target week W* (the plan week ahead) against the
prior completed week W-1's actuals, multi-week load, recovery, strength, the
Garmin plan, athlete goals and the last review — then the main session's single
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
      "load_trend": {...}|null,
      "acwr": {...}|null,
      "recovery": {"trend": {...}|null, "status": {...}|null,
                   "baseline_deviation": {...}|null},
      "strength": {"prev_week": [...]|null, "current_week": [...]|null},
      "scheduled_workouts": {...}|null,   # network (Garmin Connect); _safe/null-on-error
      "athlete_profile": {...}|null,
      "goals_with_weeks_to_race": [{...goal, "weeks_to_race": int|null}],
      "past_review": {...}|null
    }

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

from garmin_mcp.database.connection import get_connection, get_db_path
from garmin_mcp.utils.week import get_week_start_day, week_bounds

# Multi-week load lookback (matches the skill's get_load_trend(lookback_weeks=10)).
_LOAD_LOOKBACK_WEEKS = 10
# Recovery-trend window in weeks (matches the skill's get_recovery_trend(weeks=8)).
_RECOVERY_TREND_WEEKS = 8
# Fitness summary lookback (the skill uses lookback_weeks=1 for a one-week view).
_FITNESS_LOOKBACK_WEEKS = 1


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

    # Athlete profile (goals / focus) + last review, via AthleteReader.
    from garmin_mcp.database.readers.athlete import AthleteReader

    athlete_reader = AthleteReader(db_path=db_path_str)
    athlete_profile = _safe(lambda: athlete_reader.get_athlete_profile(user_id))
    past_review = _safe(lambda: athlete_reader.get_weekly_review(user_id=user_id))

    # Goals with weeks-to-race pre-computed against W's start (ceil, null-safe).
    goals = (athlete_profile or {}).get("goals") or []
    goals_with_weeks_to_race = [
        {**goal, "weeks_to_race": _weeks_to_race(goal.get("race_date"), week_start)}
        for goal in goals
    ]

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
        "scheduled_workouts": scheduled_workouts,
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
