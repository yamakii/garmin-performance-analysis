"""Training plan ledger tool definitions.

Six tools cover the two plan concepts introduced in issue #977:

- the mesocycle ledger (``save_training_blocks`` / ``get_training_blocks``),
  edited conversationally by the ``/plan-block`` skill;
- the structured weekly prescriptions (``save_weekly_prescriptions`` /
  ``get_weekly_prescriptions`` / ``update_prescription_status``), written by the
  weekly review and consumed by the daily check-in, workout scheduling and the
  monthly view;
- ``reconcile_prescriptions``, the deterministic prescription → activity linker.

Optional fields are modeled as ``T | None = None`` so the derived MCP schema
emits no ``default`` key; runtime defaults are applied in the handlers.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.analysis.workout_catalog import TEMPLATES, expand
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "default"

#: Keys a row's ``workout`` object may carry.
_WORKOUT_KEYS = frozenset({"template", "params"})


def _template_catalog_text() -> str:
    """One line per catalog template: id, session types and example params."""
    return "; ".join(
        f"{t.id} ({'|'.join(sorted(t.session_types))}: {', '.join(t.example)})"
        for t in TEMPLATES.values()
    )


def _expand_workout_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand every row's ``workout`` template into ``structure`` (Issue #1405).

    A row may name a catalog template (:mod:`garmin_mcp.analysis.workout_catalog`)
    as ``workout: {"template": str, "params": {...}}`` instead of hand-writing
    its steps. The template builds the structure and the title from the same
    parameters, so the row gets the structure, the title when it carries none,
    and the template's default purpose when it declares none. The ``workout``
    key itself is dropped before the insert.

    Args:
        rows: Prescription rows as passed to ``save_weekly_prescriptions``.

    Returns:
        New list of rows; rows without ``workout`` are returned unchanged.

    Raises:
        ValueError: Naming the row date, when ``workout`` is combined with
            ``structure`` or ``strides``, is malformed, names an unknown
            template, a template that does not fit the row's session_type, or
            parameters the template rejects.
    """
    expanded: list[dict[str, Any]] = []
    for row in rows:
        workout = row.get("workout")
        if workout is None:
            expanded.append(row)
            continue
        where = f"prescription {row.get('date')}"
        if row.get("structure") is not None or row.get("strides") is not None:
            raise ValueError(
                f"{where}: set either workout or structure / strides, not both "
                "(the template builds the structure)"
            )
        if not isinstance(workout, Mapping):
            raise ValueError(
                f"{where}: workout must be an object "
                '{"template": str, "params": {...}}'
            )
        unknown = sorted(set(workout) - _WORKOUT_KEYS)
        if unknown:
            raise ValueError(
                f"{where}: unknown workout keys {unknown} "
                f"(allowed: {sorted(_WORKOUT_KEYS)})"
            )
        template_id = workout.get("template")
        if not isinstance(template_id, str):
            raise ValueError(
                f"{where}: workout.template must be a string, got {template_id!r}"
            )
        params = workout.get("params") or {}
        try:
            structure, title = expand(template_id, params)
        except ValueError as e:
            raise ValueError(f"{where}: {e}") from e
        template = TEMPLATES[template_id]
        session_type = row.get("session_type")
        if session_type not in template.session_types:
            raise ValueError(
                f"{where}: template {template_id!r} fits session_type "
                f"{sorted(template.session_types)}, got {session_type!r}"
            )
        new_row = {k: v for k, v in row.items() if k != "workout"}
        new_row["structure"] = structure
        if not new_row.get("title"):
            new_row["title"] = title
        if new_row.get("purpose") is None:
            new_row["purpose"] = template.default_purpose
        expanded.append(new_row)
    return expanded


# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class SaveTrainingBlocksParams(BaseModel):
    """Arguments for ``save_training_blocks``."""

    blocks: list[dict[str, Any]] = Field(
        description=(
            "Full ordered list of training blocks (洗い替え — unchanged blocks "
            "must be included). Each block: phase (base|build|peak|taper|race|"
            "recovery|cutback), title, start_date, end_date (YYYY-MM-DD), and "
            "optionally purpose, weight_mode (絞る|維持), "
            "quality_sessions_per_week, quality_types (list), long_run_ladder "
            "(list of {week_start, target_km OR target_minutes, hr_ceiling, "
            "kind, note}), cutback_rule (object), notes."
        )
    )
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
    )


class GetTrainingBlocksParams(BaseModel):
    """Arguments for ``get_training_blocks``."""

    on_date: str | None = Field(
        default=None,
        description=(
            "Reference date (YYYY-MM-DD) used to resolve active_block and "
            "ladder_step. Defaults to today."
        ),
    )
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
    )


class SaveWeeklyPrescriptionsParams(BaseModel):
    """Arguments for ``save_weekly_prescriptions``."""

    week_start_date: str = Field(
        description="Week start date (YYYY-MM-DD); every row must fall in this week."
    )
    prescriptions: list[dict[str, Any]] = Field(
        description=(
            "Prescribed sessions for the week — the single source of the "
            "per-day plan, verdict included. Each row: date (YYYY-MM-DD), "
            "session_type (long|easy|recovery|threshold|tempo|rest|strength|"
            "cross), title, and optionally target_minutes, target_km, "
            "hr_low, hr_high (ceiling — the only bound for easy/long), "
            "pace_low_s_per_km, pace_high_s_per_km, rationale (the comment), "
            "rating (✅ | 🟡 | 🔴) and, on easy rows only, strides "
            '{"reps": 2-8, "run_seconds": 10-30 (default 20), '
            '"recovery_seconds": 60-180 (default 90)} — short pickups as a '
            "neuromuscular stimulus, not an interval, placed after at least "
            "5min of easy running and followed by a final 5min easy; "
            "target_minutes stays the run total and must fit 10min plus "
            "reps x (run + recovery). Every run row should also set purpose — "
            "what the run is for, finer than session_type: easy | recovery "
            "(easy/recovery rows), long_easy | long_goal_pace | "
            "long_fast_finish (long rows), progression (easy/long/tempo), "
            "tempo (tempo/threshold), intervals (threshold/tempo), fartlek "
            "(easy/tempo/threshold), race (long/tempo/threshold); a purpose "
            "that does not fit the session_type is rejected, and a row "
            "without one falls back to the session_type default (long -> "
            'long_easy). Optional allowances {"walk": true|false} states '
            "what the run permits (walk breaks); other keys are rejected. "
            "Optional structure (run rows only, never together with strides) "
            "is the workout's ordered step list: each step has step_type "
            "(warmup|run|recovery|rest|cooldown), exactly one of "
            "duration_minutes / duration_seconds / distance_m, and optionally "
            "hr_low / hr_high in integer bpm (zone labels like 'Z4' are "
            "rejected), pace_low_s_per_km / pace_high_s_per_km, label and "
            "optional (top-level run steps only); a repeat group is "
            '{"repeat_count": 1-30, "steps": [...]}, nested at most two deep. '
            "When target_minutes is omitted and every step is timed it is "
            "derived from the structure (the body only — steps other than "
            "warmup/cooldown — for threshold/tempo, the total otherwise); "
            "hr_low / hr_high are never derived. "
            'Instead of hand-writing steps, a run row may set workout {"template": '
            '<catalog id>, "params": {...}} (never together with structure or '
            "strides): the template expands into the structure, the title when "
            "the row has none and the template's purpose when it declares none "
            "(templates are listed in the tool description). "
            "Revising a week means saving a new "
            "review version first and passing its review_id: a second batch "
            "for the same review is rejected."
        )
    )
    review_id: int | None = Field(
        default=None,
        description="weekly_reviews.review_id when saved by a weekly review.",
    )
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
    )


class GetWeeklyPrescriptionsParams(BaseModel):
    """Arguments for ``get_weekly_prescriptions``."""

    week_start_date: str | None = Field(
        default=None,
        description="Week start date (YYYY-MM-DD). Give exactly one of week_start_date / date.",
    )
    date: str | None = Field(
        default=None,
        description="Single day (YYYY-MM-DD). Give exactly one of week_start_date / date.",
    )
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
    )


class UpdatePrescriptionStatusParams(BaseModel):
    """Arguments for ``update_prescription_status``."""

    prescription_id: int = Field(
        description="Prescription row identifier from get_weekly_prescriptions."
    )
    status: str = Field(
        description=(
            "New lifecycle state: prescribed | registered | done | replaced | "
            "skipped."
        )
    )
    garmin_workout_id: int | None = Field(
        default=None, description="Garmin workout id to record (optional)."
    )
    garmin_schedule_id: int | None = Field(
        default=None, description="Garmin schedule id to record (optional)."
    )
    actual_activity_id: int | None = Field(
        default=None, description="Linked actual activity id to record (optional)."
    )
    registered_bookend_minutes: int | None = Field(
        default=None,
        description=(
            "Warmup + cooldown minutes the registered workout actually carries "
            "(optional). schedule_custom_workout returns it as bookend_minutes "
            "— pass it through when linking a hand-built quality workout so "
            "reconcile_prescriptions judges against the real bookends instead "
            "of the standard 15min. schedule_weekly_prescriptions records it "
            "on its own."
        ),
    )
    structure: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "The steps of a hand-built registered workout (optional), in the "
            "same format as a prescription row's structure (hr in integer bpm, "
            "never a zone label). Pass it with status registered so the run is "
            "judged against what the watch was asked to do."
        ),
    )


class ReconcilePrescriptionsParams(BaseModel):
    """Arguments for ``reconcile_prescriptions``."""

    start_date: str = Field(description="Inclusive range start (YYYY-MM-DD).")
    end_date: str = Field(description="Inclusive range end (YYYY-MM-DD).")
    user_id: str | None = Field(
        default=None, description="Ledger owner identifier (default: 'default')"
    )


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _save_training_blocks(reader: GarminDBReader, p: SaveTrainingBlocksParams) -> Any:
    from garmin_mcp.database.inserters.plan import insert_training_blocks

    try:
        result = insert_training_blocks(
            blocks=p.blocks,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            db_path=str(reader.db_path),
        )
        return {"status": "saved", **result}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save training blocks failed: {e}")
        return {"error": str(e)}


def _get_training_blocks(reader: GarminDBReader, p: GetTrainingBlocksParams) -> Any:
    from garmin_mcp.database.readers.plan import PlanReader

    try:
        plan_reader = PlanReader(db_path=str(reader.db_path))
        user_id = p.user_id if p.user_id is not None else _DEFAULT_USER_ID
        on_date = p.on_date if p.on_date is not None else date.today().isoformat()

        week_start_date = plan_reader.resolve_week_start(on_date, user_id=user_id)
        return {
            "blocks": plan_reader.get_training_blocks(user_id=user_id),
            "active_block": plan_reader.get_block_for_date(on_date, user_id=user_id),
            "ladder_step": plan_reader.get_ladder_step_for_week(
                week_start_date, user_id=user_id
            ),
            "on_date": on_date,
            "week_start_date": week_start_date,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get training blocks failed: {e}")
        return {"error": str(e)}


def _save_weekly_prescriptions(
    reader: GarminDBReader, p: SaveWeeklyPrescriptionsParams
) -> Any:
    from garmin_mcp.database.inserters.plan import insert_weekly_prescriptions

    try:
        result = insert_weekly_prescriptions(
            week_start_date=p.week_start_date,
            prescriptions=_expand_workout_rows(p.prescriptions),
            review_id=p.review_id,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            db_path=str(reader.db_path),
        )
        return {"status": "saved", "week_start_date": p.week_start_date, **result}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save weekly prescriptions failed: {e}")
        return {"error": str(e)}


def _get_weekly_prescriptions(
    reader: GarminDBReader, p: GetWeeklyPrescriptionsParams
) -> Any:
    from garmin_mcp.database.readers.plan import PlanReader

    if (p.week_start_date is None) == (p.date is None):
        return {
            "error": "give exactly one of week_start_date / date",
            "week_start_date": p.week_start_date,
            "date": p.date,
        }

    try:
        plan_reader = PlanReader(db_path=str(reader.db_path))
        user_id = p.user_id if p.user_id is not None else _DEFAULT_USER_ID
        if p.week_start_date is not None:
            return plan_reader.get_weekly_prescriptions(
                p.week_start_date, user_id=user_id
            )
        return plan_reader.get_prescriptions_for_date(str(p.date), user_id=user_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get weekly prescriptions failed: {e}")
        return {"error": str(e)}


def _update_prescription_status(
    reader: GarminDBReader, p: UpdatePrescriptionStatusParams
) -> Any:
    from garmin_mcp.database.inserters.plan import update_prescription_status

    try:
        updated = update_prescription_status(
            prescription_id=p.prescription_id,
            status=p.status,
            garmin_workout_id=p.garmin_workout_id,
            garmin_schedule_id=p.garmin_schedule_id,
            actual_activity_id=p.actual_activity_id,
            registered_bookend_minutes=p.registered_bookend_minutes,
            structure=p.structure,
            db_path=str(reader.db_path),
        )
        return {
            "updated": updated,
            "prescription_id": p.prescription_id,
            "status": p.status if updated else None,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Update prescription status failed: {e}")
        return {"error": str(e)}


def _reconcile_prescriptions(
    reader: GarminDBReader, p: ReconcilePrescriptionsParams
) -> Any:
    from garmin_mcp.analysis.prescription_reconcile import reconcile_prescriptions

    try:
        return reconcile_prescriptions(
            start_date=p.start_date,
            end_date=p.end_date,
            user_id=p.user_id if p.user_id is not None else _DEFAULT_USER_ID,
            db_path=str(reader.db_path),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Reconcile prescriptions failed: {e}")
        return {"error": str(e)}


PLAN_TOOLS: list[ToolDef] = [
    ToolDef(
        name="save_training_blocks",
        description=(
            "Save the mesocycle ledger (training blocks) to DuckDB. Blocks are "
            "replaced wholesale per user_id (洗い替え, same as the athlete "
            "profile), so always pass the full list including unchanged blocks; "
            "sequence follows list order. Every save also appends a JSON "
            "snapshot of the whole list, so a previous plan stays recoverable. "
            "Validates the date range (start_date <= end_date), the phase, and "
            "that each long-run ladder step carries week_start plus exactly one "
            "of target_km / target_minutes. Returns {status, count, "
            "version_id}."
        ),
        params=SaveTrainingBlocksParams,
        handler=_save_training_blocks,
        cli_group="plan",
        cli_name="save-blocks",
    ),
    ToolDef(
        name="get_training_blocks",
        description=(
            "Get the mesocycle ledger with the block that is active on a given "
            "date. Returns {blocks (ordered by sequence, JSON columns decoded), "
            "active_block (the block covering on_date, or null), ladder_step "
            "({current, previous, next} long-run ladder steps for the week "
            "containing on_date, or null when no block covers it), on_date, "
            "week_start_date}. on_date defaults to today; the week is resolved "
            "with the athlete's week_start_day."
        ),
        params=GetTrainingBlocksParams,
        handler=_get_training_blocks,
        cli_group="plan",
        cli_name="get-blocks",
    ),
    ToolDef(
        name="save_weekly_prescriptions",
        description=(
            "Save one batch of prescribed sessions for a week (append-only). "
            "These rows are the single source of the per-day plan including its "
            "rating/comment; the weekly review derives its verdict from them. "
            "All rows get a fresh batch_id and the latest batch per week is "
            "canonical, so re-prescribing a week supersedes rather than mutates "
            "the earlier batch. Validates that each date falls inside the week, "
            "the session_type and rating are known, and hr_low <= hr_high. Once "
            "the week has a review, review_id must be that week's latest review "
            "version and may own only one batch — revise by saving a new review "
            "version first. A row may author its steps from a catalog template "
            'with workout {"template", "params"}; heart rate params are integer '
            "bpm (convert zones first), pace params s/km, and bookended "
            "templates also take warmup_minutes / cooldown_minutes. Templates "
            "(session types: example params): " + _template_catalog_text() + ". "
            "A Garmin registration survives the revision when a new row "
            "(status prescribed or omitted) would put the same workout on the "
            "watch as the superseded batch's registered row on that date (same "
            "title and registrable steps): the row is saved registered with the "
            "old workout/schedule ids. Judge-only edits (rationale, rating, "
            "allowances, purpose, pace bounds) keep it; changed targets, HR "
            "bounds, strides, structure or title do not. "
            "Returns {status, week_start_date, batch_id, count, "
            "prescription_ids, carried_registrations [{prescription_id, date, "
            "garmin_schedule_id}], needs_reregistration [{prescription_id, "
            "date}]} — re-register only the needs_reregistration rows with "
            "schedule_weekly_prescriptions."
        ),
        params=SaveWeeklyPrescriptionsParams,
        handler=_save_weekly_prescriptions,
        cli_group="plan",
        cli_name="save-prescriptions",
    ),
    ToolDef(
        name="get_weekly_prescriptions",
        description=(
            "Get the canonical (latest batch) prescribed sessions for a week or "
            "a single day. Give exactly one of week_start_date / date — date "
            "resolves its week with the athlete's week_start_day. Rows are "
            "ordered by date and carry targets (target_km / target_minutes), HR "
            "and pace bounds, purpose, allowances and the step structure (null "
            "when not set), "
            "status (prescribed|registered|done|replaced|"
            "skipped), the Garmin workout/schedule ids and actual_activity_id. "
            "Returns an empty list when nothing is prescribed."
        ),
        params=GetWeeklyPrescriptionsParams,
        handler=_get_weekly_prescriptions,
        cli_group="plan",
        cli_name="get-prescriptions",
    ),
    ToolDef(
        name="update_prescription_status",
        description=(
            "Update one prescription's status and optionally its Garmin workout "
            "/ schedule ids, linked activity id, registered bookend minutes and "
            "the registered workout's step structure, refreshing updated_at. Only the values you pass are written, so "
            "registering a Garmin workout and later linking the actual activity "
            "are independent updates. Returns {updated: false} when the "
            "prescription_id does not exist."
        ),
        params=UpdatePrescriptionStatusParams,
        handler=_update_prescription_status,
        cli_group="plan",
        cli_name="update-status",
    ),
    ToolDef(
        name="reconcile_prescriptions",
        description=(
            "Deterministically link prescribed sessions in a date range to the "
            "activities that actually happened, so adherence needs no LLM. For "
            "each open (prescribed / registered) latest-batch row with a past "
            "date: an activity on that date within tolerance (0.85x-1.30x of "
            "target_km / target_minutes, with quality sessions "
            "(threshold/tempo) allowed the warmup/cooldown their "
            "registered workout adds — the row's registered_bookend_minutes "
            "when recorded, else the standard 15min) marks it done, any other "
            "activity "
            "marks it replaced (a rest day with a run is always replaced), and "
            "no activity marks it skipped (rest with no activity is done). "
            "strength rows are matched against strength_sessions instead of "
            "runs, on presence alone: a session on that date marks the row "
            "done, none marks it skipped (Garmin records working time only, so "
            "a duration band would reject a circuit done as prescribed). "
            "Future dates and superseded batches are never touched. Returns "
            "{updated, done, replaced, skipped}."
        ),
        params=ReconcilePrescriptionsParams,
        handler=_reconcile_prescriptions,
        cli_group="plan",
        cli_name="reconcile",
    ),
]


PLAN_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in PLAN_TOOLS}
