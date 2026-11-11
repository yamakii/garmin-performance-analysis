"""The counterweight facts beside a fired conservative gate (Issue #1571).

When ACWR, the cutback cycle or the post-event window fires, its ``reason_ja``
says only why to hold back. This module supplies the other side as facts, from
the current-standing view (:mod:`garmin_mcp.analysis.current_standing`): what
the athlete has already proven, what the goal still requires (the remaining
long-run ladder steps up to the A race) and what holding this week back would
cost. Code supplies both sides; the reader weighs them. The gates themselves --
their existence, thresholds and verdicts -- are untouched.

Pure functions only -- the caller supplies the standing dict.
"""

from __future__ import annotations

from typing import Any

#: Gate names a caller may report as fired.
GATE_NAMES = frozenset({"acwr", "cutback_long_run", "cutback_volume", "event_window"})

#: Ladder kinds that move the long run forward (a held week shifts them back).
_BUILD_STEP_KINDS = frozenset({"build"})

_HOLD_COST_NO_GOAL_JA = (
    "目標レースが登録されていないため、今週を抑えたときに後ろへずれる"
    "ラダーの段数は算出できません。"
)


def _a_goal(goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The nearest upcoming priority-A goal view (falls back to the nearest)."""
    upcoming = [
        g
        for g in goals
        if isinstance(g, dict)
        and g.get("weeks_to_race") is not None
        and int(g["weeks_to_race"]) >= 0
    ]
    upcoming.sort(key=lambda g: (int(g["weeks_to_race"]), str(g.get("race_date"))))
    for goal in upcoming:
        if str(goal.get("priority") or "").strip().upper() == "A":
            return goal
    return upcoming[0] if upcoming else None


def _is_build_step(step: dict[str, Any]) -> bool:
    kind = str(step.get("kind") or "").strip().lower()
    return kind in _BUILD_STEP_KINDS or kind == ""


def _longest_remaining_km(steps: list[dict[str, Any]]) -> float | None:
    distances = [float(s["target_km"]) for s in steps if s.get("target_km") is not None]
    return max(distances) if distances else None


def _hold_cost_ja(goal: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """How many remaining build steps a held week pushes back.

    Holding this week delays the ladder by one week. Weeks before the race that
    carry no ladder step (``weeks_to_race - 1 - len(steps)``, the slack) absorb
    one step each; the build steps beyond the slack move back.
    """
    race_name = goal.get("race_name") or "目標レース"
    weeks = int(goal["weeks_to_race"])
    build_steps = sum(1 for s in steps if _is_build_step(s))
    slack = max(0, weeks - 1 - len(steps))
    shifted = max(0, build_steps - slack)
    if build_steps == 0:
        return (
            f"{race_name}まで{weeks}週で、残りのラダーにビルド段階はありません。"
            "今週を抑えても後ろへずれる段はありません。"
        )
    if shifted == 0:
        return (
            f"{race_name}まで{weeks}週で、残りのビルド段階は{build_steps}段、"
            f"空き週は{slack}週です。今週を抑えても空き週で吸収でき、"
            "後ろへずれる段はありません。"
        )
    return (
        f"{race_name}まで{weeks}週で、残りのビルド段階は{build_steps}段、"
        f"空き週は{slack}週です。今週を抑えると、空き週で吸収できない"
        f"{shifted}段が後ろへずれます。"
    )


def build_counterweight(standing: dict[str, Any], fired: list[str]) -> dict[str, Any]:
    """The facts that weigh against a fired gate.

    Args:
        standing: :func:`~garmin_mcp.analysis.current_standing.
            build_current_standing` output (``goals``, ``remaining_steps``,
            ``proven``).
        fired: The gates that fired, a subset of :data:`GATE_NAMES`
            (``"acwr"``, ``"cutback_long_run"``, ``"cutback_volume"``,
            ``"event_window"``). Unknown names are ignored.

    Returns:
        ``{}`` when nothing fired. Otherwise ``{"fired": [...],
        "proven": {"longest_run", "build_baseline_km"}, "goal_demand":
        {"race_name", "weeks_to_race", "remaining_steps",
        "longest_remaining_km"} | None, "hold_cost_ja": str}``.
        ``goal_demand`` is None when no upcoming goal is registered, and
        ``hold_cost_ja`` then says so.
    """
    fired_gates = [name for name in fired if name in GATE_NAMES]
    if not fired_gates:
        return {}

    proven = standing.get("proven") or {}
    goal = _a_goal(standing.get("goals") or [])
    steps = [s for s in (standing.get("remaining_steps") or []) if isinstance(s, dict)]

    if goal is None:
        goal_demand = None
        hold_cost_ja = _HOLD_COST_NO_GOAL_JA
    else:
        goal_demand = {
            "race_name": goal.get("race_name"),
            "weeks_to_race": int(goal["weeks_to_race"]),
            "remaining_steps": steps,
            "longest_remaining_km": _longest_remaining_km(steps),
        }
        hold_cost_ja = _hold_cost_ja(goal, steps)

    return {
        "fired": fired_gates,
        "proven": {
            "longest_run": proven.get("longest_run"),
            "build_baseline_km": proven.get("build_baseline_km"),
        },
        "goal_demand": goal_demand,
        "hold_cost_ja": hold_cost_ja,
    }
