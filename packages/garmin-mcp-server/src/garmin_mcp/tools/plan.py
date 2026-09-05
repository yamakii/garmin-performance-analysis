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
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "default"


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
            "Prescribed sessions for the week. Each row: date (YYYY-MM-DD), "
            "session_type (long|easy|recovery|threshold|tempo|strides|rest|"
            "strength|cross), title, and optionally target_minutes, target_km, "
            "hr_low, hr_high (ceiling — the only bound for easy/long), "
            "pace_low_s_per_km, pace_high_s_per_km, rationale."
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
            prescriptions=p.prescriptions,
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
            "All rows get a fresh batch_id and the latest batch per week is "
            "canonical, so re-prescribing a week supersedes rather than mutates "
            "the earlier batch. Validates that each date falls inside the week, "
            "the session_type is known, and hr_low <= hr_high. Returns {status, "
            "week_start_date, batch_id, count, prescription_ids}."
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
            "and pace bounds, status (prescribed|registered|done|replaced|"
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
            "/ schedule ids and linked activity id, refreshing updated_at. Only "
            "the ids you pass are written, so registering a Garmin workout and "
            "later linking the actual activity are independent updates. Returns "
            "{updated: false} when the prescription_id does not exist."
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
            "target_km / target_minutes) marks it done, any other activity "
            "marks it replaced (a rest day with a run is always replaced), and "
            "no activity marks it skipped (rest with no activity is done). "
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
