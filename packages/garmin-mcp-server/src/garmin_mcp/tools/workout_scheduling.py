"""Custom-workout scheduling tools (issue #851).

Two generic write tools let the weekly-review prescription (LLM layer) register a
session to the Garmin calendar in one call, while lifecycle management lives in
code so the self-authored library never sprawls:

- ``schedule_custom_workout(date, title, steps)`` builds a Garmin workout JSON
  from a generic ``steps`` array, force-prefixes the title with ``[MCP] ``,
  deletes any same-title ``[MCP]`` template (delete -> recreate), uploads it and
  schedules it on ``date``.
- ``cleanup_generated_workouts(dry_run=False)`` unschedules past ``[MCP]``
  assignments and deletes ``[MCP]`` templates that have no future schedule.
  Manual (non-``[MCP]``) workouts are never touched.

Run type is expressed purely as differences in ``steps`` (not as extra tools), so
the MCP ``inputSchema`` stays stable and new target kinds (pace, ...) remain a
zero-touch reload. The JSON assembly is a pure function (``build_workout_json``)
that the unit tests exercise exhaustively; live writes go through the singleton
``ApiClient`` and are mocked in tests (CI never writes to Garmin).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

# All self-authored workouts carry this title prefix so cleanup can tell them
# apart from manually-created / Garmin Coach workouts.
MCP_PREFIX = "[MCP] "

# Running sport type (the only sport this tool schedules).
_RUNNING_SPORT_TYPE: dict[str, Any] = {
    "sportTypeId": 1,
    "sportTypeKey": "running",
    "displayOrder": 1,
}

# step_type -> (stepTypeId, stepTypeKey, displayOrder). A bare "run" work step
# maps to Garmin's "interval" step type.
_STEP_TYPE_MAP: dict[str, tuple[int, str]] = {
    "warmup": (1, "warmup"),
    "cooldown": (2, "cooldown"),
    "run": (3, "interval"),
    "interval": (3, "interval"),
    "recovery": (4, "recovery"),
    "rest": (5, "rest"),
}


def _ensure_prefix(title: str) -> str:
    """Return ``title`` with the ``[MCP] `` prefix, without double-prefixing."""
    stripped = title.strip()
    if stripped.startswith(MCP_PREFIX):
        return stripped
    return f"{MCP_PREFIX}{stripped}"


def _step_type_dict(step_type: str) -> dict[str, Any]:
    """Build the ``stepType`` sub-dict for an executable step."""
    step_type_id, key = _STEP_TYPE_MAP.get(step_type, _STEP_TYPE_MAP["run"])
    return {
        "stepTypeId": step_type_id,
        "stepTypeKey": key,
        "displayOrder": step_type_id,
    }


def _end_condition(step: dict[str, Any]) -> tuple[dict[str, Any], float | None]:
    """Resolve a step's end condition + value.

    ``duration_minutes`` / ``duration_seconds`` -> time (seconds);
    ``distance_m`` -> distance (meters); otherwise a lap-button press.
    """
    if "duration_minutes" in step:
        cond = {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        }
        return cond, float(step["duration_minutes"]) * 60
    if "duration_seconds" in step:
        cond = {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        }
        return cond, float(step["duration_seconds"])
    if "distance_m" in step:
        cond = {
            "conditionTypeId": 3,
            "conditionTypeKey": "distance",
            "displayOrder": 3,
            "displayable": True,
        }
        return cond, float(step["distance_m"])
    cond = {
        "conditionTypeId": 1,
        "conditionTypeKey": "lap.button",
        "displayOrder": 1,
        "displayable": True,
    }
    return cond, None


def _target_fields(step: dict[str, Any]) -> dict[str, Any]:
    """Build the target-type fields for an executable step.

    When both ``hr_low`` and ``hr_high`` are present the step targets a custom
    heart-rate range (``heart.rate.zone`` with ``targetValueOne/Two`` in bpm);
    otherwise it carries no target.
    """
    hr_low = step.get("hr_low")
    hr_high = step.get("hr_high")
    if hr_low is not None and hr_high is not None:
        return {
            "targetType": {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 4,
            },
            "targetValueOne": hr_low,
            "targetValueTwo": hr_high,
        }
    return {
        "targetType": {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }
    }


def _build_executable_step(step: dict[str, Any], step_order: int) -> dict[str, Any]:
    """Build one ``ExecutableStepDTO`` dict."""
    condition, value = _end_condition(step)
    built: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": _step_type_dict(str(step.get("step_type", "run"))),
        "endCondition": condition,
    }
    if value is not None:
        built["endConditionValue"] = value
    built.update(_target_fields(step))
    return built


def _build_any_step(
    step: dict[str, Any], step_order: int
) -> tuple[dict[str, Any], int]:
    """Build a single step (executable or repeat group).

    Returns the built dict and the next available ``stepOrder`` (a running
    counter shared across the whole workout, including repeat-group children).
    """
    if "repeat_count" in step:
        return _build_repeat_group(step, step_order)
    return _build_executable_step(step, step_order), step_order + 1


def _build_repeat_group(
    step: dict[str, Any], step_order: int
) -> tuple[dict[str, Any], int]:
    """Build a ``RepeatGroupDTO`` dict from ``{repeat_count, steps: [...]}``."""
    child_order = step_order + 1
    children: list[dict[str, Any]] = []
    for child in step.get("steps", []):
        built, child_order = _build_any_step(child, child_order)
        children.append(built)
    iterations = int(step["repeat_count"])
    group = {
        "type": "RepeatGroupDTO",
        "stepOrder": step_order,
        "stepType": {
            "stepTypeId": 6,
            "stepTypeKey": "repeat",
            "displayOrder": 6,
        },
        "numberOfIterations": iterations,
        "smartRepeat": False,
        "endCondition": {
            "conditionTypeId": 7,
            "conditionTypeKey": "iterations",
            "displayOrder": 7,
            "displayable": False,
        },
        "endConditionValue": float(iterations),
        "workoutSteps": children,
    }
    return group, child_order


def _estimate_seconds(step: dict[str, Any]) -> float:
    """Best-effort duration estimate in seconds (distance steps contribute 0)."""
    if "repeat_count" in step:
        inner = sum(_estimate_seconds(c) for c in step.get("steps", []))
        return int(step["repeat_count"]) * inner
    if "duration_minutes" in step:
        return float(step["duration_minutes"]) * 60
    if "duration_seconds" in step:
        return float(step["duration_seconds"])
    return 0.0


def build_workout_json(title: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a Garmin workout-service upload JSON from generic steps.

    Pure function (the core unit-tested surface). ``title`` is force-prefixed
    with ``[MCP] ``; ``steps`` is an ordered list where each entry is either an
    executable step (``step_type`` + one of ``duration_minutes`` /
    ``duration_seconds`` / ``distance_m``, optional ``hr_low`` / ``hr_high``) or
    a repeat group (``repeat_count`` + nested ``steps``).
    """
    workout_steps: list[dict[str, Any]] = []
    order = 1
    estimated = 0.0
    for step in steps:
        built, order = _build_any_step(step, order)
        workout_steps.append(built)
        estimated += _estimate_seconds(step)

    return {
        "workoutName": _ensure_prefix(title),
        "sportType": dict(_RUNNING_SPORT_TYPE),
        "estimatedDurationInSecs": int(estimated),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": dict(_RUNNING_SPORT_TYPE),
                "workoutSteps": workout_steps,
            }
        ],
    }


# ----------------------------------------------------------------------------
# Calendar assignment collection + cleanup planning
# ----------------------------------------------------------------------------


def _enumerate_year_months(start: date, end: date) -> list[tuple[int, int]]:
    """Enumerate (year, 1-indexed month) pairs spanning [start, end] inclusive."""
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def _collect_mcp_assignments(
    client: Any, window_days: int = 180
) -> list[dict[str, Any]]:
    """Collect scheduled ``[MCP]`` calendar assignments around today.

    Scans every month spanning [today - window_days, today + window_days] via the
    Garmin calendar-service (garminconnect's ``get_scheduled_workouts`` takes a
    1-indexed month) and returns workout-type items whose title carries the
    ``[MCP]`` prefix, each as ``{schedule_id, workout_id, date, title}``.
    """
    today = date.today()
    start = today - timedelta(days=window_days)
    end = today + timedelta(days=window_days)

    assignments: list[dict[str, Any]] = []
    for year, month in _enumerate_year_months(start, end):
        payload = client.get_scheduled_workouts(year, month)
        items = (payload or {}).get("calendarItems") or []
        for item in items:
            if item.get("itemType") != "workout":
                continue
            title = item.get("title") or ""
            if not title.startswith(MCP_PREFIX):
                continue
            assignments.append(
                {
                    "schedule_id": item.get("id"),
                    "workout_id": item.get("workoutId"),
                    "date": item.get("date"),
                    "title": title,
                }
            )
    return assignments


def _plan_cleanup(
    templates: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    today: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decide which assignments to unschedule and which templates to delete.

    Pure decision function: past-dated ``[MCP]`` assignments are unscheduled;
    ``[MCP]`` templates with no future schedule are deleted. Templates without
    the ``[MCP]`` prefix are ignored entirely.
    """
    to_unschedule: list[dict[str, Any]] = []
    future_workout_ids: set[Any] = set()
    for assignment in assignments:
        raw_date = assignment.get("date")
        try:
            scheduled_date = date.fromisoformat(str(raw_date))
        except ValueError:
            logger.warning("Skipping assignment with bad date: %r", raw_date)
            continue
        if scheduled_date < today:
            to_unschedule.append(assignment)
        else:
            future_workout_ids.add(assignment.get("workout_id"))

    mcp_templates = [
        w for w in templates if str(w.get("workoutName", "")).startswith(MCP_PREFIX)
    ]
    to_delete = [
        w for w in mcp_templates if w.get("workoutId") not in future_workout_ids
    ]
    return to_unschedule, to_delete


# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class ScheduleCustomWorkoutParams(BaseModel):
    """Arguments for ``schedule_custom_workout``."""

    date: str = Field(description="Target date to schedule on (YYYY-MM-DD)")
    title: str = Field(
        description=(
            "Workout title. A '[MCP] ' prefix is force-added (not doubled) so the "
            "cleanup tool can distinguish self-authored workouts."
        )
    )
    steps: list[dict[str, Any]] = Field(
        description=(
            "Ordered workout steps. Each entry is either an executable step "
            "(step_type of warmup/run/recovery/cooldown, one of duration_minutes, "
            "duration_seconds or distance_m, and optional hr_low/hr_high for a "
            "custom HR-range target) or a repeat group (repeat_count + nested "
            "steps)."
        )
    )


class CleanupGeneratedWorkoutsParams(BaseModel):
    """Arguments for ``cleanup_generated_workouts``."""

    dry_run: bool = Field(
        default=False,
        description=(
            "When True, only report the assignments/templates that would be "
            "removed without performing any write."
        ),
    )


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _schedule_custom_workout(
    reader: GarminDBReader, p: ScheduleCustomWorkoutParams
) -> Any:
    from garmin_mcp.ingest.api_client import get_garmin_client

    try:
        client = get_garmin_client()
        title = _ensure_prefix(p.title)

        # Delete any same-title [MCP] template first (delete -> recreate) so the
        # self-authored library keeps at most one template per title.
        replaced: list[Any] = []
        for workout in client.get_workouts() or []:
            if workout.get("workoutName") == title:
                client.delete_workout(workout.get("workoutId"))
                replaced.append(workout.get("workoutId"))

        workout_json = build_workout_json(p.title, p.steps)
        uploaded = client.upload_workout(workout_json)
        workout_id = uploaded.get("workoutId") if isinstance(uploaded, dict) else None

        scheduled = client.schedule_workout(workout_id, p.date)
        schedule_id = None
        if isinstance(scheduled, dict):
            schedule_id = scheduled.get("workoutScheduleId") or scheduled.get("id")

        return {
            "workout_id": workout_id,
            "schedule_id": schedule_id,
            "date": p.date,
            "title": title,
            "replaced_workout_ids": replaced,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_custom_workout failed: {e}")
        return {"error": str(e)}


def _cleanup_generated_workouts(
    reader: GarminDBReader, p: CleanupGeneratedWorkoutsParams
) -> Any:
    from garmin_mcp.ingest.api_client import get_garmin_client

    try:
        client = get_garmin_client()
        templates = client.get_workouts() or []
        assignments = _collect_mcp_assignments(client)
        to_unschedule, to_delete = _plan_cleanup(templates, assignments, date.today())

        if p.dry_run:
            return {
                "dry_run": True,
                "would_unschedule": to_unschedule,
                "would_delete": [
                    {"workout_id": w.get("workoutId"), "title": w.get("workoutName")}
                    for w in to_delete
                ],
            }

        unscheduled: list[Any] = []
        for assignment in to_unschedule:
            client.unschedule_workout(assignment.get("schedule_id"))
            unscheduled.append(assignment.get("schedule_id"))

        deleted: list[Any] = []
        for workout in to_delete:
            client.delete_workout(workout.get("workoutId"))
            deleted.append(workout.get("workoutId"))

        return {
            "dry_run": False,
            "unscheduled_schedule_ids": unscheduled,
            "deleted_workout_ids": deleted,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"cleanup_generated_workouts failed: {e}")
        return {"error": str(e)}


WORKOUT_SCHEDULING_TOOLS: list[ToolDef] = [
    ToolDef(
        name="schedule_custom_workout",
        description=(
            "Build a Garmin running workout from a generic steps array, force-"
            "prefix its title with '[MCP] ', replace any same-title [MCP] "
            "template (delete -> recreate), upload it and schedule it on date. "
            "Each step is an executable step (step_type warmup/run/recovery/"
            "cooldown; one of duration_minutes, duration_seconds or distance_m; "
            "optional hr_low/hr_high for a custom heart-rate-range target) or a "
            "repeat group (repeat_count + nested steps). Returns {workout_id, "
            "schedule_id, date, title, replaced_workout_ids}."
        ),
        params=ScheduleCustomWorkoutParams,
        handler=_schedule_custom_workout,
        cli_group="workout",
        cli_name="schedule",
    ),
    ToolDef(
        name="cleanup_generated_workouts",
        description=(
            "Tidy self-authored [MCP] workouts: unschedule past-dated [MCP] "
            "calendar assignments and delete [MCP] templates that have no future "
            "schedule. Never touches manual (non-[MCP]) workouts. Pass "
            "dry_run=True to only list what would be removed."
        ),
        params=CleanupGeneratedWorkoutsParams,
        handler=_cleanup_generated_workouts,
        cli_group="workout",
        cli_name="cleanup",
    ),
]


WORKOUT_SCHEDULING_TOOLS_BY_NAME: dict[str, ToolDef] = {
    d.name: d for d in WORKOUT_SCHEDULING_TOOLS
}
