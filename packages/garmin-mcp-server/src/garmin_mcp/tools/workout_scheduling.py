"""Custom-workout scheduling tools (issues #851, #981).

Three generic write tools let the weekly-review prescription (LLM layer) register
sessions to the Garmin calendar, while lifecycle management lives in code so the
self-authored library never sprawls:

- ``schedule_custom_workout(date, title, steps)`` builds a Garmin workout JSON
  from a generic ``steps`` array, force-prefixes the title with ``[MCP] ``,
  deletes any same-title ``[MCP]`` template (delete -> recreate), uploads it and
  schedules it on ``date``.
- ``schedule_weekly_prescriptions(week_start_date, ...)`` does the same for a
  whole week of ``weekly_prescriptions`` rows: it derives the steps from each
  row in code (``build_steps_from_prescription``), registers every registrable
  session and records ``garmin_workout_id`` / ``garmin_schedule_id`` plus
  ``status=registered`` back on the row. ``dry_run=True`` (the default) returns
  the exact plan — titles, steps and same-day Garmin conflicts — so the skill can
  show it before the single confirmation the batch needs.
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

# Non-alerting floor used when a step prescribes a ceiling (``hr_high``) only.
# Garmin's heart-rate target is always a range, so a ceiling-only prescription
# needs some floor; 80 bpm sits below any running heart rate, so the low-HR
# alert can never fire and the ceiling still governs (#979).
_DEFAULT_HR_FLOOR = 80

# Ledger owner used when the caller does not name one.
_DEFAULT_USER_ID = "default"

# Shape of a prescription-derived workout: every session gets the same easy
# warmup / cooldown bookends so the body step carries the prescribed target only.
_WARMUP_MINUTES = 10
_COOLDOWN_MINUTES = 5

# Strides are prescribed as a shape, not as a target: 5 x 20s pickups with 90s
# easy recovery, none of which carries an HR target (they are too short for HR
# to settle).
_STRIDES_REPEAT_COUNT = 5
_STRIDES_RUN_SECONDS = 20
_STRIDES_RECOVERY_SECONDS = 90

# Prescription session types that map onto a Garmin running workout. rest /
# strength / cross are prescribed but never registered as a run.
_REGISTRABLE_TYPES = frozenset(
    {"long", "easy", "recovery", "threshold", "tempo", "strides"}
)

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

    ``hr_low`` + ``hr_high`` -> a custom heart-rate range (``heart.rate.zone``
    with ``targetValueOne/Two`` in bpm).

    ``hr_high`` alone -> the same range target with ``_DEFAULT_HR_FLOOR`` as the
    floor. Ceiling-only prescriptions (Z2 / easy / long runs, which must never be
    pushed by a low-HR alert) previously fell through to ``no.target``, so the
    ceiling never reached the watch (#979).

    ``hr_low`` alone or neither bound -> no target.
    """
    hr_low = step.get("hr_low")
    hr_high = step.get("hr_high")
    if hr_high is not None:
        return {
            "targetType": {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 4,
            },
            "targetValueOne": hr_low if hr_low is not None else _DEFAULT_HR_FLOOR,
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
    a repeat group (``repeat_count`` + nested ``steps``). Giving ``hr_high``
    alone yields a ceiling-governed HR target (see ``_target_fields``).
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


def build_steps_from_prescription(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the generic ``steps`` array from one ``weekly_prescriptions`` row.

    Pure function, so the whole prescription -> workout mapping is unit-tested
    without touching Garmin. Every session is bookended by a 10-minute warmup and
    a 5-minute cooldown with no target; only the body step carries the
    prescription's own bounds:

    - ``long`` / ``easy`` / ``recovery``: one body step ending on
      ``target_minutes`` (preferred, time-managed runs) or ``target_km``
      converted to meters, with ``hr_high`` as a ceiling. ``hr_low`` is written
      only when the row actually prescribes a floor, so ceiling-only easy/long
      runs never get a low-HR alert (#979).
    - ``threshold`` / ``tempo``: the same shape; these rows carry both bounds, so
      the body step becomes a real HR range.
    - ``strides``: a 5x(20s run / 90s recovery) repeat group instead of a body
      step (no distance/duration target needed).

    Args:
        p: A prescription row (``session_type``, ``target_minutes`` /
            ``target_km``, ``hr_low`` / ``hr_high``).

    Returns:
        Steps ready for ``build_workout_json`` / ``schedule_custom_workout``.

    Raises:
        ValueError: When ``session_type`` is not registrable as a run, or when a
            non-strides session prescribes neither ``target_minutes`` nor
            ``target_km``.
    """
    session_type = str(p.get("session_type") or "")
    if session_type not in _REGISTRABLE_TYPES:
        raise ValueError(
            f"session_type {session_type!r} is not registrable as a run "
            f"(registrable: {sorted(_REGISTRABLE_TYPES)})"
        )

    warmup = {"step_type": "warmup", "duration_minutes": _WARMUP_MINUTES}
    cooldown = {"step_type": "cooldown", "duration_minutes": _COOLDOWN_MINUTES}

    if session_type == "strides":
        return [
            warmup,
            {
                "repeat_count": _STRIDES_REPEAT_COUNT,
                "steps": [
                    {"step_type": "run", "duration_seconds": _STRIDES_RUN_SECONDS},
                    {
                        "step_type": "recovery",
                        "duration_seconds": _STRIDES_RECOVERY_SECONDS,
                    },
                ],
            },
            cooldown,
        ]

    body: dict[str, Any] = {"step_type": "run"}
    target_minutes = p.get("target_minutes")
    target_km = p.get("target_km")
    if target_minutes is not None:
        body["duration_minutes"] = target_minutes
    elif target_km is not None:
        body["distance_m"] = round(float(target_km) * 1000)
    else:
        raise ValueError(
            f"session_type {session_type!r} needs target_minutes or target_km "
            "to build a workout"
        )

    hr_low = p.get("hr_low")
    hr_high = p.get("hr_high")
    if hr_low is not None:
        body["hr_low"] = hr_low
    if hr_high is not None:
        body["hr_high"] = hr_high

    return [warmup, body, cooldown]


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

    The calendar service repeats the same item within a single month payload
    (every entry of a real 2026-07/08 query came back exactly twice), so results
    are de-duplicated by ``schedule_id`` in first-seen order. Without that the
    caller unschedules one id twice and the second call 404s (#880). Items
    without a ``schedule_id`` are dropped: they cannot be unscheduled.
    """
    today = date.today()
    start = today - timedelta(days=window_days)
    end = today + timedelta(days=window_days)

    assignments: dict[Any, dict[str, Any]] = {}
    for year, month in _enumerate_year_months(start, end):
        payload = client.get_scheduled_workouts(year, month)
        items = (payload or {}).get("calendarItems") or []
        for item in items:
            if item.get("itemType") != "workout":
                continue
            title = item.get("title") or ""
            if not title.startswith(MCP_PREFIX):
                continue
            schedule_id = item.get("id")
            if schedule_id is None or schedule_id in assignments:
                continue
            assignments[schedule_id] = {
                "schedule_id": schedule_id,
                "workout_id": item.get("workoutId"),
                "date": item.get("date"),
                "title": title,
            }
    return list(assignments.values())


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
# Registration (shared by the single-session and weekly-batch tools)
# ----------------------------------------------------------------------------


def _register_workout(
    client: Any,
    *,
    on_date: str,
    title: str,
    steps: list[dict[str, Any]],
    templates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replace any same-title ``[MCP]`` template, upload and schedule a workout.

    Args:
        client: Authenticated Garmin client.
        on_date: Target date (``YYYY-MM-DD``).
        title: Workout title (the ``[MCP] `` prefix is force-added).
        steps: Generic steps array for ``build_workout_json``.
        templates: Pre-fetched ``client.get_workouts()`` payload. The weekly
            batch fetches the library once and reuses it across items; passing
            ``None`` fetches it here.

    Returns:
        ``{workout_id, schedule_id, date, title, replaced_workout_ids}``.
    """
    full_title = _ensure_prefix(title)

    # Delete any same-title [MCP] template first (delete -> recreate) so the
    # self-authored library keeps at most one template per title.
    library = templates if templates is not None else (client.get_workouts() or [])
    replaced: list[Any] = []
    for workout in library:
        if workout.get("workoutName") == full_title:
            client.delete_workout(workout.get("workoutId"))
            replaced.append(workout.get("workoutId"))

    uploaded = client.upload_workout(build_workout_json(title, steps))
    workout_id = uploaded.get("workoutId") if isinstance(uploaded, dict) else None

    scheduled = client.schedule_workout(workout_id, on_date)
    schedule_id = None
    if isinstance(scheduled, dict):
        schedule_id = scheduled.get("workoutScheduleId") or scheduled.get("id")

    return {
        "workout_id": workout_id,
        "schedule_id": schedule_id,
        "date": on_date,
        "title": full_title,
        "replaced_workout_ids": replaced,
    }


def _plan_week_registrations(
    rows: list[dict[str, Any]], explicit_ids: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a week's prescriptions into registrable items and skipped rows.

    Pure decision function (no Garmin, no DB). A row is skipped when its
    ``session_type`` is not a run, when its targets cannot build a workout, or
    when it is already registered on Garmin — the last case only unless the
    caller named it in ``explicit_ids``, which means "re-register / replace".

    Args:
        rows: Canonical prescriptions for the week (reader order).
        explicit_ids: ``prescription_ids`` the caller asked for. When non-empty,
            rows outside the set are not considered at all.

    Returns:
        ``(items, skipped)`` where each item is ``{prescription_id, date, title,
        steps, already_registered}`` and each skip is ``{prescription_id,
        reason}``.
    """
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in rows:
        prescription_id = row.get("prescription_id")
        if explicit_ids and prescription_id not in explicit_ids:
            continue

        session_type = str(row.get("session_type") or "")
        already_registered = (
            row.get("status") == "registered"
            and row.get("garmin_schedule_id") is not None
        )
        if already_registered and prescription_id not in explicit_ids:
            skipped.append(
                {
                    "prescription_id": prescription_id,
                    "reason": (
                        "already registered on Garmin (pass its prescription_id "
                        "to re-register)"
                    ),
                }
            )
            continue

        try:
            steps = build_steps_from_prescription(row)
        except ValueError as e:
            skipped.append({"prescription_id": prescription_id, "reason": str(e)})
            continue

        items.append(
            {
                "prescription_id": prescription_id,
                "date": str(row.get("date")),
                "title": str(row.get("title") or session_type),
                "steps": steps,
                "already_registered": already_registered,
            }
        )

    return items, skipped


def _existing_titles_by_date(week_start_date: str) -> dict[str, list[str]]:
    """Map each day of the week to the non-``[MCP]`` Garmin items scheduled on it.

    Garmin Coach / adaptive / manual assignments are reported as conflicts, never
    deleted: only same-title ``[MCP]`` templates are replaced.

    Args:
        week_start_date: Week start (``YYYY-MM-DD``).

    Returns:
        ``{date: [title, ...]}`` for the 7 days starting at ``week_start_date``.
    """
    from garmin_mcp.fitness.garmin_calendar import GarminCalendarReader

    start = date.fromisoformat(week_start_date)
    end = start + timedelta(days=6)
    scheduled = GarminCalendarReader().get_scheduled_workouts(
        start.isoformat(), end.isoformat()
    )

    by_date: dict[str, list[str]] = {}
    for item in scheduled:
        title = str(item.get("title") or "")
        if title.startswith(MCP_PREFIX):
            continue
        by_date.setdefault(str(item.get("date")), []).append(title)
    return by_date


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


class ScheduleWeeklyPrescriptionsParams(BaseModel):
    """Arguments for ``schedule_weekly_prescriptions``."""

    week_start_date: str = Field(
        description="Week start date (YYYY-MM-DD) of the prescriptions to register."
    )
    prescription_ids: list[int] | None = Field(
        default=None,
        description=(
            "Register only these prescription_ids (subset of the week). Naming "
            "an already-registered row re-registers it. Defaults to every "
            "registrable row of the week's latest batch."
        ),
    )
    dry_run: bool | None = Field(
        default=None,
        description=(
            "When True (the default), return the plan (titles, steps, same-day "
            "Garmin conflicts) without writing anything to Garmin."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
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
        return _register_workout(client, on_date=p.date, title=p.title, steps=p.steps)
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_custom_workout failed: {e}")
        return {"error": str(e)}


def _schedule_weekly_prescriptions(
    reader: GarminDBReader, p: ScheduleWeeklyPrescriptionsParams
) -> Any:
    from garmin_mcp.database.inserters.plan import update_prescription_status
    from garmin_mcp.database.readers.plan import PlanReader
    from garmin_mcp.ingest.api_client import get_garmin_client

    dry_run = True if p.dry_run is None else p.dry_run
    user_id = p.user_id if p.user_id is not None else _DEFAULT_USER_ID

    try:
        rows = PlanReader(db_path=str(reader.db_path)).get_weekly_prescriptions(
            p.week_start_date, user_id=user_id
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_weekly_prescriptions failed to read the week: {e}")
        return {"error": str(e)}

    items, skipped = _plan_week_registrations(rows, set(p.prescription_ids or []))

    if dry_run:
        result: dict[str, Any] = {
            "dry_run": True,
            "week_start_date": p.week_start_date,
            "items": items,
            "skipped": skipped,
        }
        try:
            existing = _existing_titles_by_date(p.week_start_date)
        except Exception as e:  # noqa: BLE001
            # A calendar hiccup must not hide the plan; report it instead of
            # silently claiming there are no conflicts.
            logger.warning("Could not read the Garmin calendar: %s", e)
            existing = {}
            result["calendar_error"] = str(e)
        for item in items:
            item["existing_same_day"] = existing.get(item["date"], [])
        return result

    try:
        client = get_garmin_client()
        templates = client.get_workouts() or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_weekly_prescriptions failed to reach Garmin: {e}")
        return {"error": str(e)}

    # Each item is isolated: one upload failure (rate limit, bad target) must
    # leave the already-registered days in place and let the rest proceed.
    registered: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in items:
        prescription_id = item["prescription_id"]
        try:
            outcome = _register_workout(
                client,
                on_date=item["date"],
                title=item["title"],
                steps=item["steps"],
                templates=templates,
            )
            update_prescription_status(
                prescription_id=prescription_id,
                status="registered",
                garmin_workout_id=outcome["workout_id"],
                garmin_schedule_id=outcome["schedule_id"],
                db_path=str(reader.db_path),
            )
            registered.append(
                {
                    "prescription_id": prescription_id,
                    "workout_id": outcome["workout_id"],
                    "schedule_id": outcome["schedule_id"],
                    "date": outcome["date"],
                    "title": outcome["title"],
                }
            )
        except Exception as e:  # noqa: BLE001
            # The row id stays out of the log line: CodeQL treats anything named
            # "prescription" as private data (py/clear-text-logging-sensitive-data).
            # The id is returned to the caller in `failed` instead.
            logger.warning("Registering one weekly prescription failed: %s", e)
            failed.append({"prescription_id": prescription_id, "error": str(e)})

    return {
        "dry_run": False,
        "week_start_date": p.week_start_date,
        "registered": registered,
        "failed": failed,
        "skipped": skipped,
    }


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

        # Each removal is isolated: one stale id (already dropped in the Garmin
        # app, or a duplicate that slipped through) must not abort the rest of
        # the cleanup, which previously left the template deletions unexecuted
        # (#880).
        unscheduled: list[Any] = []
        failed_unschedule: list[dict[str, Any]] = []
        for assignment in to_unschedule:
            schedule_id = assignment.get("schedule_id")
            try:
                client.unschedule_workout(schedule_id)
                unscheduled.append(schedule_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("unschedule_workout(%r) failed: %s", schedule_id, e)
                failed_unschedule.append({"schedule_id": schedule_id, "error": str(e)})

        deleted: list[Any] = []
        failed_delete: list[dict[str, Any]] = []
        for workout in to_delete:
            workout_id = workout.get("workoutId")
            try:
                client.delete_workout(workout_id)
                deleted.append(workout_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("delete_workout(%r) failed: %s", workout_id, e)
                failed_delete.append({"workout_id": workout_id, "error": str(e)})

        return {
            "dry_run": False,
            "unscheduled_schedule_ids": unscheduled,
            "deleted_workout_ids": deleted,
            "failed_unschedule": failed_unschedule,
            "failed_delete": failed_delete,
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
        name="schedule_weekly_prescriptions",
        description=(
            "Register a whole week of saved prescriptions to the Garmin "
            "calendar in one batch. Steps are derived in code from each row "
            "(10min warmup, body on target_minutes or target_km with hr_high as "
            "a ceiling and hr_low only when prescribed, 5min cooldown; strides "
            "become 5x20s pickups); rest/strength/cross rows and rows already "
            "registered are skipped, and naming an id in prescription_ids "
            "re-registers it. dry_run=True (default) returns {dry_run, "
            "week_start_date, items ({prescription_id, date, title, steps, "
            "existing_same_day, already_registered}), skipped} so the plan can "
            "be confirmed first. dry_run=False registers each item (delete "
            "same-title [MCP] template -> upload -> schedule), records the "
            "workout/schedule ids with status=registered on the row, isolates "
            "per-item failures and returns {dry_run, week_start_date, "
            "registered, failed, skipped}."
        ),
        params=ScheduleWeeklyPrescriptionsParams,
        handler=_schedule_weekly_prescriptions,
        cli_group="workout",
        cli_name="schedule-week",
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
