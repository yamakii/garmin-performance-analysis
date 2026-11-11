"""Where the athlete stands against the goal, as one deterministic view (#1569).

Every coaching surface used to anchor on its own inputs (the run report, raw
load statistics or profile prose, which goes stale). This module assembles a
single dict from the reader outputs instead: the active goals with their goal
pace and weeks to race, the block phase and week position, the remaining
long-run ladder steps up to the A goal, what the athlete has already proven
(longest recent run, build baseline) and the recent runs near a goal pace.

Pace bands are not invented: the only pace used is ``target_time_seconds /
distance_km``. No PB / season-best detection (owner decision on #1564).

Pure functions only -- the reader supplies every input.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

#: A run counts as "near goal pace" within this many s/km of a goal pace.
NEAR_GOAL_PACE_TOLERANCE_SEC = 15.0

#: Runs shorter than this are too short to say anything about goal pace.
NEAR_GOAL_PACE_MIN_KM = 5.0

#: How far back ``recent_runs`` reaches (the reader's window).
RECENT_WINDOW_DAYS = 28

MISSING_NO_ACTIVE_GOAL = "no active goal"
MISSING_NO_BLOCK = "no block covers on_date"
MISSING_NO_GOAL_PACE = "no goal has a target time"
MISSING_NO_LONG_RUN = "no long run on record"
MISSING_NO_BUILD_BASELINE = "no build baseline"


def _parse_date(value: Any) -> date | None:
    """Parse ``YYYY-MM-DD`` (or a ``date``) into a ``date``; None on failure."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def goal_pace_sec_per_km(goal: dict[str, Any]) -> float | None:
    """``target_time_seconds / distance_km`` rounded to 0.1, or None."""
    target = goal.get("target_time_seconds")
    distance = goal.get("distance_km")
    if target is None or distance is None:
        return None
    distance_km = float(distance)
    if distance_km <= 0:
        return None
    return round(float(target) / distance_km, 1)


def weeks_to_race(on_date: date, race_date: Any) -> int | None:
    """Whole weeks from ``on_date`` to ``race_date`` (ceiling), or None."""
    race = _parse_date(race_date)
    if race is None:
        return None
    return math.ceil((race - on_date).days / 7)


def _goal_view(goal: dict[str, Any], on_date: date) -> dict[str, Any]:
    distance = goal.get("distance_km")
    return {
        "race_name": goal.get("race_name"),
        "race_date": (
            str(goal["race_date"]) if goal.get("race_date") is not None else None
        ),
        "priority": goal.get("priority"),
        "distance_km": float(distance) if distance is not None else None,
        "target_time_seconds": goal.get("target_time_seconds"),
        "goal_pace_sec_per_km": goal_pace_sec_per_km(goal),
        "weeks_to_race": weeks_to_race(on_date, goal.get("race_date")),
    }


def _a_goal(goals: list[dict[str, Any]], on_date: date) -> dict[str, Any] | None:
    """The nearest upcoming priority-A goal (falls back to the nearest goal)."""
    upcoming = [
        g
        for g in goals
        if (race := _parse_date(g.get("race_date"))) is not None and race >= on_date
    ]
    upcoming.sort(key=lambda g: str(g.get("race_date")))
    for goal in upcoming:
        if str(goal.get("priority") or "").strip().upper() == "A":
            return goal
    return upcoming[0] if upcoming else None


def _covering_block(
    on_date: date, blocks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for block in blocks:
        start = _parse_date(block.get("start_date"))
        end = _parse_date(block.get("end_date"))
        if start is not None and end is not None and start <= on_date <= end:
            return block
    return None


def _ladder_steps(block: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [
        s
        for s in (block.get("long_run_ladder") or [])
        if isinstance(s, dict) and _parse_date(s.get("week_start")) is not None
    ]
    return sorted(steps, key=lambda s: str(s["week_start"]))


def _step_view(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if step is None:
        return None
    target_km = step.get("target_km")
    return {
        "week_start": str(step.get("week_start")),
        "target_km": float(target_km) if target_km is not None else None,
        "kind": step.get("kind"),
    }


def _current_step_index(steps: list[dict[str, Any]], on_date: date) -> int | None:
    """Index of the ladder step whose week (7 days from week_start) holds on_date."""
    for index, step in enumerate(steps):
        start = _parse_date(step.get("week_start"))
        if start is not None and start <= on_date < start + timedelta(days=7):
            return index
    return None


def _block_view(block: dict[str, Any], on_date: date) -> dict[str, Any]:
    start = _parse_date(block.get("start_date"))
    end = _parse_date(block.get("end_date"))
    week_position: dict[str, int] | None = None
    if start is not None and end is not None:
        week_position = {
            "week": (on_date - start).days // 7 + 1,
            "of": math.ceil(((end - start).days + 1) / 7),
        }
    steps = _ladder_steps(block)
    index = _current_step_index(steps, on_date)
    if index is None:
        current = None
        later = [
            s
            for s in steps
            if (ws := _parse_date(s.get("week_start"))) is not None and ws > on_date
        ]
        next_step = later[0] if later else None
    else:
        current = steps[index]
        next_step = steps[index + 1] if index + 1 < len(steps) else None
    return {
        "title": block.get("title"),
        "phase": block.get("phase"),
        "purpose": block.get("purpose"),
        "week_position": week_position,
        "current_step": _step_view(current),
        "next_step": _step_view(next_step),
    }


def _remaining_steps(
    blocks: list[dict[str, Any]],
    on_date: date,
    a_goal: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Ladder steps after the current week, up to the A goal's race date."""
    race = _parse_date(a_goal.get("race_date")) if a_goal is not None else None
    current_week_end = on_date
    for block in blocks:
        steps = _ladder_steps(block)
        index = _current_step_index(steps, on_date)
        if index is not None:
            current_week_end = _parse_date(steps[index]["week_start"]) or on_date
            break

    remaining: dict[str, dict[str, Any]] = {}
    for block in blocks:
        for step in _ladder_steps(block):
            week = _parse_date(step.get("week_start"))
            if week is None or week <= current_week_end:
                continue
            if race is not None and week > race:
                continue
            view = _step_view(step)
            if view is not None:
                remaining.setdefault(view["week_start"], view)
    return [remaining[key] for key in sorted(remaining)]


def _near_goal_pace(
    recent_runs: list[dict[str, Any]], goals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    paced = [
        (goal_pace, goal.get("race_name"))
        for goal in goals
        if (goal_pace := goal_pace_sec_per_km(goal)) is not None
    ]
    if not paced:
        return []
    near: list[dict[str, Any]] = []
    for run in recent_runs:
        distance = run.get("distance_km")
        pace = run.get("avg_pace_sec_per_km")
        if distance is None or pace is None:
            continue
        if float(distance) < NEAR_GOAL_PACE_MIN_KM:
            continue
        diff, goal_pace, goal_name = min(
            (abs(float(pace) - gp), gp, name) for gp, name in paced
        )
        if diff > NEAR_GOAL_PACE_TOLERANCE_SEC:
            continue
        near.append(
            {
                "date": str(run.get("date")),
                "distance_km": round(float(distance), 2),
                "pace": round(float(pace), 1),
                "goal": goal_name,
                "goal_pace_sec_per_km": goal_pace,
                "training_type": run.get("training_type"),
            }
        )
    near.sort(key=lambda r: r["date"])
    return near


def build_current_standing(
    on_date: str,
    goals: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    proven_long_run: dict[str, Any] | None,
    build_baseline: dict[str, Any],
    recent_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble where the athlete stands against the goal on ``on_date``.

    Args:
        on_date: Reference day (``YYYY-MM-DD``).
        goals: ``athlete_goals`` rows with status ``active``.
        blocks: ``PlanReader.get_training_blocks()`` rows.
        proven_long_run: The longest recent run (reader output) or None.
        build_baseline: ``compute_build_baseline(...)`` output.
        recent_runs: Runs of the last 28 days, each ``{date, distance_km,
            avg_pace_sec_per_km, avg_hr, training_type}``.

    Returns:
        ``{"on_date", "goals", "block", "remaining_steps", "proven",
        "recent_near_goal_pace", "missing"}``. ``goals`` carry
        ``goal_pace_sec_per_km`` (target / distance; None without a target) and
        ``weeks_to_race``; ``block`` is None when no block covers ``on_date``;
        ``remaining_steps`` are the ladder steps after the current week up to
        the A goal; ``recent_near_goal_pace`` holds runs >= 5 km within
        +/-15 s/km of a goal pace; ``missing`` names every absent input.
    """
    day = _parse_date(on_date)
    if day is None:
        raise ValueError(f"on_date must be YYYY-MM-DD, got {on_date!r}")

    missing: list[str] = []

    goal_views = [_goal_view(goal, day) for goal in goals]
    goal_views.sort(key=lambda g: (g["race_date"] is None, g["race_date"] or ""))
    if not goals:
        missing.append(MISSING_NO_ACTIVE_GOAL)
    elif all(g["goal_pace_sec_per_km"] is None for g in goal_views):
        missing.append(MISSING_NO_GOAL_PACE)

    block = _covering_block(day, blocks)
    if block is None:
        missing.append(MISSING_NO_BLOCK)

    if proven_long_run is None:
        missing.append(MISSING_NO_LONG_RUN)

    baseline_km = (build_baseline or {}).get("weekly_km")
    if baseline_km is None:
        missing.append(MISSING_NO_BUILD_BASELINE)

    return {
        "on_date": day.isoformat(),
        "goals": goal_views,
        "block": _block_view(block, day) if block is not None else None,
        "remaining_steps": _remaining_steps(blocks, day, _a_goal(goals, day)),
        "proven": {
            "longest_run": proven_long_run,
            "build_baseline_km": (
                float(baseline_km) if baseline_km is not None else None
            ),
        },
        "recent_near_goal_pace": _near_goal_pace(recent_runs, goals),
        "missing": missing,
    }
