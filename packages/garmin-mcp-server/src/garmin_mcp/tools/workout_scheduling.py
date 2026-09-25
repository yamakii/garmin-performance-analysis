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

Both scheduling tools run that same tidy (``_run_cleanup``) *before* uploading
anything, so a stale ``[MCP]`` item can no longer survive on the watch just
because nobody remembered the manual cleanup (#1065); a cleanup failure is
reported but never aborts the registration, and dry runs report what would be
cleaned instead. Every library read pages through ``get_workouts``
(``_fetch_library``): the default ``limit=100`` used to hide any template past
position 100 from replacement and cleanup.

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

from garmin_mcp.analysis.prescription_shape import (
    BOOKENDED_TYPES,
    bookend_minutes_from_steps,
)
from garmin_mcp.analysis.workout_structure import (
    RUN_SESSION_TYPES,
    registrable_steps,
    synthesize_structure,
)
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

# All self-authored workouts carry this title prefix so cleanup can tell them
# apart from manually-created / Garmin Coach workouts.
MCP_PREFIX = "[MCP] "

# Page size for the workout-library listing. ``get_workouts`` defaults to
# ``limit=100`` while the real library holds a few hundred workouts, so every
# read pages through it (:func:`_fetch_library`); a bare call would hide every
# template past position 100 from replacement and cleanup (#1065).
_LIBRARY_PAGE_SIZE = 100

# Non-alerting floor used when a step prescribes a ceiling (``hr_high``) only.
# Garmin's heart-rate target is always a range, so a ceiling-only prescription
# needs some floor; 80 bpm sits below any running heart rate, so the low-HR
# alert can never fire and the ceiling still governs (#979).
_DEFAULT_HR_FLOOR = 80

# Sub-sport stamped on every uploaded workout. Unlike ``sportType`` (a dict),
# the workout-service takes ``subSportType`` as a bare FIT ``sub_sport``
# integer: 0=GENERIC, 1=TREADMILL, 2=STREET, 3=TRAIL, 4=TRACK (a dict is
# rejected with HTTP 500, a string with HTTP 400, and this is NOT the
# activity-service id space -- 7 there is ``street_running`` but stores as the
# cycling sub-sport ``ROAD``). Leaving it unset stores ``null``, and the watch
# then asks which activity type to run every time a scheduled workout is
# started (#1100). These are road runs, so STREET.
_STREET_SUB_SPORT = 2

# Ledger owner used when the caller does not name one.
_DEFAULT_USER_ID = "default"

# Statuses the reconciler sets once a row has been matched against the day's
# run: the day is over, so the row is never registered again by default.
_RECONCILED_STATUSES = frozenset({"done", "replaced", "skipped"})

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
        "subSportType": _STREET_SUB_SPORT,
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

    Registration reads the same structure the judge does:
    :func:`~garmin_mcp.analysis.workout_structure.synthesize_structure` builds
    it (a stored ``structure`` wins; legacy rows are synthesized from their
    columns — single body step for easy-effort runs, strides block on an easy
    row, warmup/cooldown bookends on threshold / tempo) and
    :func:`~garmin_mcp.analysis.workout_structure.registrable_steps` drops the
    optional steps and judge-only keys the watch never sees.

    Args:
        p: A prescription row (``session_type``, ``target_minutes`` /
            ``target_km``, ``hr_low`` / ``hr_high``, optional ``strides`` /
            ``structure``).

    Returns:
        Steps ready for ``build_workout_json`` / ``schedule_custom_workout``.

    Raises:
        ValueError: When ``session_type`` is not registrable as a run, when a
            session prescribes neither ``target_minutes`` nor ``target_km``,
            when an easy row's strides do not fit inside ``target_minutes``, or
            when a stored structure is invalid.
    """
    session_type = str(p.get("session_type") or "")
    if session_type not in RUN_SESSION_TYPES:
        raise ValueError(
            f"session_type {session_type!r} is not registrable as a run "
            f"(registrable: {sorted(RUN_SESSION_TYPES)})"
        )
    structure = synthesize_structure(p)
    if structure is None:
        raise ValueError(
            f"session_type {session_type!r} needs target_minutes or target_km "
            "to build a workout"
        )
    return registrable_steps(structure)


def _registered_bookend_minutes(
    row: dict[str, Any], steps: list[dict[str, Any]]
) -> int | None:
    """Return the bookend minutes to record for a row registered from ``steps``.

    Only bookended session types (threshold / tempo) add minutes on top of
    ``target_minutes``. An easy run with strides ends on a 5-minute easy
    ``cooldown`` step, but that step is part of the prescribed total, so it
    must not widen the reconciliation band: non-bookended rows record ``0``.
    """
    if str(row.get("session_type") or "") not in BOOKENDED_TYPES:
        return 0
    return bookend_minutes_from_steps(steps)


def _custom_bookend_minutes(steps: list[dict[str, Any]]) -> int | None:
    """Return the bookend minutes to record for a hand-built registration.

    A hand-built workout has no ``session_type``, so the shape stands in for it:
    only a workout that opens with a ``warmup`` is bookended (the threshold /
    tempo shape). An easy run with strides ends on a 5-minute easy ``cooldown``
    step that is part of the prescribed total, so it records ``0`` like the
    weekly path does. ``None`` for empty steps, as
    :func:`bookend_minutes_from_steps`.
    """
    if not steps:
        return None
    if not any(s.get("step_type") == "warmup" for s in steps):
        return 0
    return bookend_minutes_from_steps(steps)


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


def _fetch_library(client: Any) -> list[dict[str, Any]]:
    """Return **every** workout in the Garmin library.

    ``client.get_workouts()`` serves one page (default ``limit=100``) of a
    library that really holds a few hundred workouts, so a bare call silently
    hides everything past position 100: a same-title replacement, an id-based
    replacement (#1042) or a cleanup scan would never see an ``[MCP]`` template
    that drifted down the list (#1065). Pages ``get_workouts(start, 100)`` from
    0 until a page shorter than the page size (or empty) comes back, which is
    robust even if the service does not guarantee a stable order across pages.
    """
    library: list[dict[str, Any]] = []
    start = 0
    while True:
        page = client.get_workouts(start, _LIBRARY_PAGE_SIZE) or []
        library.extend(page)
        if len(page) < _LIBRARY_PAGE_SIZE:
            return library
        start += _LIBRARY_PAGE_SIZE


def _preview_cleanup(
    client: Any,
    today: date,
    *,
    templates: list[dict[str, Any]] | None = None,
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Report what a cleanup would remove, without writing anything."""
    library = templates if templates is not None else _fetch_library(client)
    scheduled = (
        assignments if assignments is not None else _collect_mcp_assignments(client)
    )
    to_unschedule, to_delete = _plan_cleanup(library, scheduled, today)
    return {
        "would_unschedule": to_unschedule,
        "would_delete": [
            {"workout_id": w.get("workoutId"), "title": w.get("workoutName")}
            for w in to_delete
        ],
    }


def _run_cleanup(
    client: Any,
    today: date,
    *,
    templates: list[dict[str, Any]] | None = None,
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Unschedule past ``[MCP]`` assignments and delete orphan ``[MCP]`` templates.

    The live body shared by ``cleanup_generated_workouts`` (the manual entry
    point) and the pre-registration hook both scheduling tools run, so the tidy
    never depends on a human remembering it (#1065).

    Each removal is isolated: one stale id (already dropped in the Garmin app,
    or a duplicate that slipped through) must not abort the rest of the cleanup,
    which previously left the template deletions unexecuted (#880).

    Args:
        client: Authenticated Garmin client.
        today: Reference date. ``scheduled_date < today`` is "past", so today's
            own assignment is never unscheduled.
        templates: Pre-fetched library (see :func:`_fetch_library`); the weekly
            batch fetches it once and reuses it for the registrations.
        assignments: Pre-fetched ``[MCP]`` calendar assignments.

    Returns:
        ``{unscheduled_schedule_ids, deleted_workout_ids, failed_unschedule,
        failed_delete}``.
    """
    library = templates if templates is not None else _fetch_library(client)
    scheduled = (
        assignments if assignments is not None else _collect_mcp_assignments(client)
    )
    to_unschedule, to_delete = _plan_cleanup(library, scheduled, today)

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
        "unscheduled_schedule_ids": unscheduled,
        "deleted_workout_ids": deleted,
        "failed_unschedule": failed_unschedule,
        "failed_delete": failed_delete,
    }


def _cleanup_before_registration(
    client: Any,
    *,
    templates: list[dict[str, Any]] | None = None,
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run :func:`_run_cleanup` before a registration, never raising.

    A cleanup hiccup (calendar fetch failure, an id that vanished) must never
    abort the registration the user actually asked for: the error is reported in
    the result instead.
    """
    try:
        return _run_cleanup(
            client, date.today(), templates=templates, assignments=assignments
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Pre-registration [MCP] cleanup failed: %s", e)
        return {"error": str(e)}


def _library_without(
    templates: list[dict[str, Any]], deleted_workout_ids: Any
) -> list[dict[str, Any]]:
    """Drop the workouts a cleanup just deleted from a pre-fetched library."""
    deleted = set(deleted_workout_ids or [])
    if not deleted:
        return templates
    return [w for w in templates if w.get("workoutId") not in deleted]


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
    replace_workout_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Replace the superseded ``[MCP]`` workouts, upload and schedule a new one.

    Two replacement rules run together (deduped, so one workout is deleted at
    most once):

    1. any ``[MCP]`` template whose title equals the new one — keeps the
       self-authored library at one template per title;
    2. ``replace_workout_ids`` — workouts previously recorded for this slot
       (a re-registered row, or the same day in a superseded batch).
       Re-registering a revised row under a *new* title would otherwise leave
       the old template scheduled on the same day (#1042).

    Only ``[MCP]``-prefixed workouts are ever deleted: an id that is unknown to
    the library or carries a manual title is skipped and reported instead.

    Args:
        client: Authenticated Garmin client.
        on_date: Target date (``YYYY-MM-DD``).
        title: Workout title (the ``[MCP] `` prefix is force-added).
        steps: Generic steps array for ``build_workout_json``.
        templates: Pre-fetched library (:func:`_fetch_library`). The weekly
            batch fetches the library once and reuses it across items; passing
            ``None`` fetches (and pages) it here.
        replace_workout_ids: Workout ids recorded for this slot, each deleted
            before the upload when it names an ``[MCP]`` template.

    Returns:
        ``{workout_id, schedule_id, date, title, replaced_workout_ids,
        skipped_replace_ids}``.
    """
    full_title = _ensure_prefix(title)

    # Decide the deletions first (delete -> recreate), then perform them, so an
    # id that is also the same-title template is never deleted twice.
    library = templates if templates is not None else _fetch_library(client)
    to_delete: list[Any] = [
        w.get("workoutId") for w in library if w.get("workoutName") == full_title
    ]
    skipped_replace_ids: list[Any] = []

    for replace_id in replace_workout_ids or []:
        recorded = next((w for w in library if w.get("workoutId") == replace_id), None)
        recorded_name = str((recorded or {}).get("workoutName") or "")
        if recorded is not None and recorded_name.startswith(MCP_PREFIX):
            if replace_id not in to_delete:
                to_delete.append(replace_id)
        else:
            # Foreign or already-gone id: never delete a workout we did not author.
            skipped_replace_ids.append(replace_id)

    replaced: list[Any] = []
    for workout_id in to_delete:
        client.delete_workout(workout_id)
        replaced.append(workout_id)

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
        "skipped_replace_ids": skipped_replace_ids,
    }


def _plan_week_registrations(
    rows: list[dict[str, Any]],
    explicit_ids: set[int],
    superseded_by_date: dict[str, list[int]] | None = None,
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
        superseded_by_date: Workouts registered from the week's older batches
            (:meth:`PlanReader.get_superseded_workout_ids`).

    Returns:
        ``(items, skipped)`` where each item is ``{prescription_id, date, title,
        steps, bookend_minutes, already_registered, replace_workout_ids}``
        (``bookend_minutes`` is what the registration records, see
        :func:`_registered_bookend_minutes`) and each skip is
        ``{prescription_id, reason}``. ``replace_workout_ids`` carries the
        workout recorded on an explicitly re-registered row plus, on the first
        item of a date, the workouts superseded batches registered that day, so
        the old items leave the calendar even when the revised title differs
        (#1042).
    """
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    superseded = dict(superseded_by_date or {})

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
        status = str(row.get("status") or "")
        if status in _RECONCILED_STATUSES and prescription_id not in explicit_ids:
            skipped.append(
                {
                    "prescription_id": prescription_id,
                    "reason": f"already reconciled with the day's run ({status})",
                }
            )
            continue

        try:
            steps = build_steps_from_prescription(row)
        except ValueError as e:
            skipped.append({"prescription_id": prescription_id, "reason": str(e)})
            continue

        on_date = str(row.get("date"))
        replace_ids: list[int] = []
        recorded = row.get("garmin_workout_id")
        if prescription_id in explicit_ids and recorded is not None:
            replace_ids.append(int(recorded))
        # Popped, so a second item on the same day never deletes the same id.
        for workout_id in superseded.pop(on_date, []):
            if workout_id not in replace_ids:
                replace_ids.append(workout_id)

        items.append(
            {
                "prescription_id": prescription_id,
                "date": on_date,
                "title": str(row.get("title") or session_type),
                "steps": steps,
                "bookend_minutes": _registered_bookend_minutes(row, steps),
                "already_registered": already_registered,
                "replace_workout_ids": replace_ids,
            }
        )

    return items, skipped


def _stale_superseded(
    rows: list[dict[str, Any]],
    items: list[dict[str, Any]],
    superseded_by_date: dict[str, list[int]],
) -> list[dict[str, Any]]:
    """Superseded workouts on days the new batch no longer runs.

    A day is covered when an item registers on it now or a row of the new
    batch is already registered or reconciled on it. Workouts on uncovered
    days are never
    deleted by a registration (nothing replaces them), so they are reported
    for the caller to raise with the athlete. Some may already be gone from
    Garmin (deleted by hand or by the cleanup).

    Returns:
        ``[{date, workout_ids}]`` ascending by date.
    """
    covered = {item["date"] for item in items} | {
        str(row.get("date"))
        for row in rows
        if (row.get("status") == "registered" and row.get("garmin_schedule_id"))
        or row.get("status") in _RECONCILED_STATUSES
    }
    return [
        {"date": on_date, "workout_ids": ids}
        for on_date, ids in sorted(superseded_by_date.items())
        if on_date not in covered
    ]


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
        # Tidy first, so a stale [MCP] template/assignment never survives a
        # registration just because nobody ran the cleanup tool (#1065).
        templates = _fetch_library(client)
        cleanup = _cleanup_before_registration(client, templates=templates)
        result = _register_workout(
            client,
            on_date=p.date,
            title=p.title,
            steps=p.steps,
            templates=_library_without(templates, cleanup.get("deleted_workout_ids")),
        )
        result["cleanup"] = cleanup
        # Hand-built steps are exactly the case the constant cannot describe, so
        # hand the caller the real figure to record on the row (Issue #1087).
        result["bookend_minutes"] = _custom_bookend_minutes(p.steps)
        return result
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
        plan_reader = PlanReader(db_path=str(reader.db_path))
        rows = plan_reader.get_weekly_prescriptions(p.week_start_date, user_id=user_id)
        superseded = plan_reader.get_superseded_workout_ids(
            p.week_start_date, user_id=user_id
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_weekly_prescriptions failed to read the week: {e}")
        return {"error": str(e)}

    explicit_ids = set(p.prescription_ids or [])
    items, skipped = _plan_week_registrations(rows, explicit_ids, superseded)
    # A partial re-registration leaves the other days alone on purpose, so only
    # a whole-week run can tell which superseded days the new batch dropped.
    stale = [] if explicit_ids else _stale_superseded(rows, items, superseded)

    if dry_run:
        result: dict[str, Any] = {
            "dry_run": True,
            "week_start_date": p.week_start_date,
            "items": items,
            "skipped": skipped,
            "stale_superseded": stale,
        }
        try:
            existing = _existing_titles_by_date(p.week_start_date)
        except Exception as e:  # noqa: BLE001
            # A calendar hiccup must not hide the plan; report it instead of
            # silently claiming there are no conflicts.
            logger.warning("Could not read the Garmin calendar: %s", e)
            existing = {}
            result["calendar_error"] = str(e)
        try:
            # A dry run writes nothing, so the cleanup the live run would
            # perform first is reported instead of executed.
            result["would_cleanup"] = _preview_cleanup(
                get_garmin_client(), date.today()
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not preview the [MCP] cleanup: %s", e)
            result["would_cleanup"] = {"error": str(e)}
        for item in items:
            item["existing_same_day"] = existing.get(item["date"], [])
            # A dry run replaces nothing: report the ids instead of promising it.
            item["would_replace_workout_ids"] = item.pop("replace_workout_ids", [])
        return result

    try:
        client = get_garmin_client()
        templates = _fetch_library(client)
    except Exception as e:  # noqa: BLE001
        logger.error(f"schedule_weekly_prescriptions failed to reach Garmin: {e}")
        return {"error": str(e)}

    # Tidy before uploading anything, so stale [MCP] items never survive a
    # registration just because nobody ran the cleanup tool (#1065). The library
    # is reused for the registrations minus whatever the cleanup just deleted.
    cleanup = _cleanup_before_registration(client, templates=templates)
    templates = _library_without(templates, cleanup.get("deleted_workout_ids"))

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
                replace_workout_ids=item.get("replace_workout_ids"),
            )
            update_prescription_status(
                prescription_id=prescription_id,
                status="registered",
                garmin_workout_id=outcome["workout_id"],
                garmin_schedule_id=outcome["schedule_id"],
                registered_bookend_minutes=item["bookend_minutes"],
                db_path=str(reader.db_path),
            )
            registered.append(
                {
                    "prescription_id": prescription_id,
                    "workout_id": outcome["workout_id"],
                    "schedule_id": outcome["schedule_id"],
                    "date": outcome["date"],
                    "title": outcome["title"],
                    "replaced_workout_ids": outcome["replaced_workout_ids"],
                    "skipped_replace_ids": outcome["skipped_replace_ids"],
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
        "cleanup": cleanup,
        "registered": registered,
        "failed": failed,
        "skipped": skipped,
        "stale_superseded": stale,
    }


def _cleanup_generated_workouts(
    reader: GarminDBReader, p: CleanupGeneratedWorkoutsParams
) -> Any:
    from garmin_mcp.ingest.api_client import get_garmin_client

    try:
        client = get_garmin_client()
        if p.dry_run:
            return {"dry_run": True, **_preview_cleanup(client, date.today())}
        # Same runner the scheduling tools invoke before every registration; this
        # tool stays the manual entry point for tidying without registering.
        return {"dry_run": False, **_run_cleanup(client, date.today())}
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
            "Runs the [MCP] cleanup first (unschedule past-dated [MCP] "
            "assignments, delete [MCP] templates with no future schedule), so "
            "stale items never linger; a cleanup failure never aborts the "
            "registration. Each step is an executable step (step_type warmup/run/"
            "recovery/cooldown; one of duration_minutes, duration_seconds or "
            "distance_m; optional hr_low/hr_high for a custom heart-rate-range "
            "target) or a repeat group (repeat_count + nested steps). Returns "
            "{workout_id, schedule_id, date, title, replaced_workout_ids, "
            "skipped_replace_ids, cleanup, bookend_minutes}. bookend_minutes is "
            "the value to record on the prescription row: the warmup + cooldown "
            "minutes when the steps open with a warmup (a threshold / tempo "
            "shape), else 0 (an easy run with strides ends on a 5min easy step "
            "that is part of its total)."
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
            "calendar in one batch. Steps are derived in code from each row: "
            "long/easy/recovery become a single body step on target_minutes or "
            "target_km (hr_high as a ceiling, hr_low only when prescribed) so "
            "the watch asks for exactly what was prescribed; an easy row with "
            "a strides add-on becomes an opening easy step, a repeat group of "
            "reps x (run_seconds stride / recovery_seconds jog, no HR target) "
            "and a final 5min easy step, together exactly target_minutes (the "
            "run total). Quality sessions (threshold/tempo) keep a 10min "
            "warmup and a 5min cooldown around the body; "
            "rest/strength/cross rows, rows already "
            "registered and rows already reconciled with a run (done / "
            "replaced / skipped) are skipped, and naming an id in "
            "prescription_ids re-registers it. dry_run=True (default) returns {dry_run, "
            "week_start_date, items ({prescription_id, date, title, steps, "
            "bookend_minutes, existing_same_day, already_registered, "
            "would_replace_workout_ids}), would_cleanup, skipped, "
            "stale_superseded} so the plan can be confirmed first. "
            "dry_run=False runs the [MCP] cleanup "
            "first (unschedule past-dated [MCP] assignments, delete [MCP] "
            "templates with no future schedule; a cleanup failure never aborts "
            "the batch), then registers each item (delete the "
            "same-title [MCP] template, the [MCP] workout already recorded "
            "on a re-registered row AND the [MCP] workouts the week's "
            "superseded batches registered on that day, so a revised title "
            "never leaves the old item on the calendar -> upload -> schedule), "
            "records the "
            "workout/schedule ids with status=registered on the row, isolates "
            "per-item failures and returns {dry_run, week_start_date, cleanup, "
            "registered, failed, skipped, stale_superseded}. stale_superseded "
            "[{date, workout_ids}] lists superseded workouts on days the new "
            "batch no longer runs: they are never deleted, only reported (empty "
            "when prescription_ids narrows the run)."
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
            "schedule. Never touches manual (non-[MCP]) workouts. The same tidy "
            "runs automatically before every schedule_custom_workout / "
            "schedule_weekly_prescriptions registration, so this tool is only "
            "needed to tidy without registering. Pass dry_run=True to only list "
            "what would be removed."
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
