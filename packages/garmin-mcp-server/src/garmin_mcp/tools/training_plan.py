"""Training-plan domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.

Most tools use ``input_schema_override`` because their original hand schemas
describe optional fields without emitting JSON ``default`` keys (and ``plan`` /
``review`` are free-form ``object`` params). The Pydantic models still validate
arguments and drive the CLI signature.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)

# Safety limits for volume progression (2-tier)
VOLUME_WARNING_THRESHOLD_PCT = 0.15  # 15% warning threshold
VOLUME_HARD_LIMIT_PCT = 0.25  # 25% hard limit

# Workout types prohibited for return_to_run plans
_RETURN_TO_RUN_PROHIBITED_TYPES = {
    "tempo",
    "threshold",
    "interval",
    "repetition",
    "race_pace",
}


# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class CurrentFitnessSummaryParams(BaseModel):
    """Arguments for ``get_current_fitness_summary``."""

    lookback_weeks: int = 8


class SaveTrainingPlanParams(BaseModel):
    """Arguments for ``save_training_plan``."""

    plan: dict[str, Any]


class GetTrainingPlanParams(BaseModel):
    """Arguments for ``get_training_plan``."""

    plan_id: str
    version: int | None = None
    week_number: int | None = None
    summary_only: bool = False


class UploadWorkoutParams(BaseModel):
    """Arguments for ``upload_workout_to_garmin``."""

    workout_id: str | None = None
    plan_id: str | None = None
    week_number: int | None = None
    schedule: bool = True


class DeleteWorkoutParams(BaseModel):
    """Arguments for ``delete_workout_from_garmin``."""

    workout_id: str | None = None
    plan_id: str | None = None
    week_number: int | None = None


class GarminScheduledWorkoutsParams(BaseModel):
    """Arguments for ``get_garmin_scheduled_workouts``."""

    start_date: str
    end_date: str


# ----------------------------------------------------------------------------
# Hand-written inputSchema overrides
# ----------------------------------------------------------------------------

_CURRENT_FITNESS_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lookback_weeks": {
            "type": "integer",
            "description": "Number of weeks to analyze (default: 8)",
        },
    },
}

_SAVE_TRAINING_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "object",
            "description": "TrainingPlan JSON conforming to the Pydantic model schema (plan_id, goal_type, vdot, pace_zones, total_weeks, start_date, weekly_volumes, phases, workouts, etc.)",
        },
    },
    "required": ["plan"],
}

_GET_TRAINING_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_id": {
            "type": "string",
            "description": "Plan identifier",
        },
        "version": {
            "type": "integer",
            "description": "Specific version to retrieve. Omit for latest active version.",
        },
        "week_number": {
            "type": "integer",
            "description": "Specific week to retrieve (optional)",
        },
        "summary_only": {
            "type": "boolean",
            "description": "If true, exclude individual workouts (default: false)",
        },
    },
    "required": ["plan_id"],
}

_UPLOAD_WORKOUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workout_id": {
            "type": "string",
            "description": "Single workout ID to upload",
        },
        "plan_id": {
            "type": "string",
            "description": "Plan ID to upload all workouts from",
        },
        "week_number": {
            "type": "integer",
            "description": "Specific week to upload (with plan_id)",
        },
        "schedule": {
            "type": "boolean",
            "description": "Schedule workouts on Garmin Connect calendar (default: true)",
            "default": True,
        },
    },
}

_DELETE_WORKOUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workout_id": {
            "type": "string",
            "description": "Single workout ID to delete",
        },
        "plan_id": {
            "type": "string",
            "description": "Plan ID to delete all workouts from",
        },
        "week_number": {
            "type": "integer",
            "description": "Specific week to delete (with plan_id)",
        },
    },
}

_GARMIN_SCHEDULED_WORKOUTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start_date": {
            "type": "string",
            "description": "Inclusive start date (YYYY-MM-DD)",
        },
        "end_date": {
            "type": "string",
            "description": "Inclusive end date (YYYY-MM-DD)",
        },
    },
    "required": ["start_date", "end_date"],
}


# ----------------------------------------------------------------------------
# Safety validation (moved verbatim from TrainingPlanHandler)
# ----------------------------------------------------------------------------


def _validate_plan_safety(plan: Any) -> tuple[list[str], list[str]]:
    """Run safety checks on a training plan.

    Returns (errors, warnings). Errors block saving; warnings are included in the
    success response but do not prevent saving.
    """
    errors: list[str] = []
    warnings: list[str] = []

    volumes = plan.weekly_volumes
    for i in range(1, len(volumes)):
        if volumes[i - 1] > 0:
            increase = (volumes[i] - volumes[i - 1]) / volumes[i - 1]
            if increase > VOLUME_HARD_LIMIT_PCT:
                errors.append(
                    f"Week {i} to {i + 1}: volume increase "
                    f"{increase:.1%} exceeds {VOLUME_HARD_LIMIT_PCT:.0%} hard limit "
                    f"({volumes[i - 1]:.1f}km → {volumes[i]:.1f}km)"
                )
            elif increase > VOLUME_WARNING_THRESHOLD_PCT:
                warnings.append(
                    f"Week {i} to {i + 1}: volume increase "
                    f"{increase:.1%} exceeds {VOLUME_WARNING_THRESHOLD_PCT:.0%} guideline "
                    f"({volumes[i - 1]:.1f}km → {volumes[i]:.1f}km)"
                )

    if plan.goal_type.value == "return_to_run":
        for w in plan.workouts:
            if w.workout_type.value in _RETURN_TO_RUN_PROHIBITED_TYPES:
                errors.append(
                    f"return_to_run plan contains prohibited workout type "
                    f"'{w.workout_type.value}' in week {w.week_number}"
                )

    if plan.start_date:
        from datetime import timedelta

        for w in plan.workouts:
            if w.workout_date is not None:
                expected_week_start = plan.start_date + timedelta(
                    weeks=w.week_number - 1
                )
                expected_week_end = expected_week_start + timedelta(days=6)
                if not (expected_week_start <= w.workout_date <= expected_week_end):
                    errors.append(
                        f"Workout {w.workout_id} date {w.workout_date} "
                        f"is outside week {w.week_number} range "
                        f"({expected_week_start} - {expected_week_end})"
                    )

    return errors, warnings


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _get_current_fitness_summary(
    reader: GarminDBReader, p: CurrentFitnessSummaryParams
) -> Any:
    from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor

    try:
        assessor = FitnessAssessor(db_path=str(reader.db_path))
        summary = assessor.assess(lookback_weeks=p.lookback_weeks)
        return summary.model_dump()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fitness assessment failed: {e}")
        return {"error": str(e)}


def _save_training_plan(reader: GarminDBReader, p: SaveTrainingPlanParams) -> Any:
    from garmin_mcp.database.inserters.training_plans import insert_training_plan
    from garmin_mcp.training_plan.models import TrainingPlan

    try:
        plan = TrainingPlan.model_validate(p.plan)

        errors, warnings = _validate_plan_safety(plan)
        if errors:
            return {"error": "Safety validation failed", "details": errors}

        insert_training_plan(db_path=str(reader.db_path), plan=plan)

        from garmin_mcp.utils.paths import get_result_dir

        plans_dir = get_result_dir() / "training_plans"
        date_str = str(plan.start_date) if plan.start_date else "unknown"
        md_filename = f"{date_str}_{plan.plan_id}.md"

        result: dict[str, Any] = {
            "status": "saved",
            "plan_id": plan.plan_id,
            "version": plan.version,
            "workout_count": len(plan.workouts),
            "markdown_path": str(plans_dir / md_filename),
        }
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save training plan failed: {e}")
        return {"error": str(e)}


def _get_training_plan(reader: GarminDBReader, p: GetTrainingPlanParams) -> Any:
    from garmin_mcp.database.readers.training_plans import TrainingPlanReader

    try:
        plan_reader = TrainingPlanReader(db_path=str(reader.db_path))
        return plan_reader.get_training_plan(
            plan_id=p.plan_id,
            version=p.version,
            week_number=p.week_number,
            summary_only=p.summary_only,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get training plan failed: {e}")
        return {"error": str(e)}


def _upload_workout_to_garmin(reader: GarminDBReader, p: UploadWorkoutParams) -> Any:
    from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader

    try:
        uploader = GarminWorkoutUploader(db_path=str(reader.db_path))
        if p.workout_id is not None:
            return uploader.upload_workout(p.workout_id, schedule=p.schedule)
        if p.plan_id is not None:
            return uploader.upload_plan_workouts(
                p.plan_id, week_number=p.week_number, schedule=p.schedule
            )
        return {"error": "Either workout_id or plan_id is required"}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Garmin upload failed: {e}")
        return {"error": str(e)}


def _delete_workout_from_garmin(reader: GarminDBReader, p: DeleteWorkoutParams) -> Any:
    from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader

    try:
        uploader = GarminWorkoutUploader(db_path=str(reader.db_path))
        if p.workout_id is not None:
            return uploader.delete_workout(p.workout_id)
        if p.plan_id is not None:
            return uploader.delete_plan_workouts(p.plan_id, week_number=p.week_number)
        return {"error": "Either workout_id or plan_id is required"}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Garmin delete failed: {e}")
        return {"error": str(e)}


def _get_garmin_scheduled_workouts(
    reader: GarminDBReader, p: GarminScheduledWorkoutsParams
) -> Any:
    from garmin_mcp.training_plan.garmin_calendar import GarminCalendarReader

    try:
        calendar_reader = GarminCalendarReader()
        workouts = calendar_reader.get_scheduled_workouts(p.start_date, p.end_date)
        return {
            "start_date": p.start_date,
            "end_date": p.end_date,
            "count": len(workouts),
            "workouts": workouts,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Get Garmin scheduled workouts failed: {e}")
        return {"error": str(e)}


TRAINING_PLAN_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_current_fitness_summary",
        description=(
            "Get current fitness level assessment (VDOT, pace zones, weekly "
            "volume, training type distribution)"
        ),
        params=CurrentFitnessSummaryParams,
        handler=_get_current_fitness_summary,
        cli_group="training-plan",
        cli_name="fitness-summary",
        input_schema_override=_CURRENT_FITNESS_SUMMARY_SCHEMA,
    ),
    ToolDef(
        name="save_training_plan",
        description=(
            "Save a training plan (structured JSON) to DuckDB. Validates schema "
            "and safety constraints (volume progression <= 15%, return_to_run "
            "restrictions, date alignment)."
        ),
        params=SaveTrainingPlanParams,
        handler=_save_training_plan,
        cli_group="training-plan",
        cli_name="save-plan",
        input_schema_override=_SAVE_TRAINING_PLAN_SCHEMA,
    ),
    ToolDef(
        name="get_training_plan",
        description="Get a previously generated training plan",
        params=GetTrainingPlanParams,
        handler=_get_training_plan,
        cli_group="training-plan",
        cli_name="get-plan",
        input_schema_override=_GET_TRAINING_PLAN_SCHEMA,
    ),
    ToolDef(
        name="upload_workout_to_garmin",
        description="Upload workout(s) to Garmin Connect",
        params=UploadWorkoutParams,
        handler=_upload_workout_to_garmin,
        cli_group="training-plan",
        cli_name="upload-workout",
        input_schema_override=_UPLOAD_WORKOUT_SCHEMA,
    ),
    ToolDef(
        name="delete_workout_from_garmin",
        description="Delete workout(s) from Garmin Connect",
        params=DeleteWorkoutParams,
        handler=_delete_workout_from_garmin,
        cli_group="training-plan",
        cli_name="delete-workout",
        input_schema_override=_DELETE_WORKOUT_SCHEMA,
    ),
    ToolDef(
        name="get_garmin_scheduled_workouts",
        description=(
            "Fetch scheduled workouts (including adaptive plan workouts) from the "
            "Garmin Connect calendar-service for a date range. Returns "
            "workout-type calendar items sorted by date."
        ),
        params=GarminScheduledWorkoutsParams,
        handler=_get_garmin_scheduled_workouts,
        cli_group="training-plan",
        cli_name="scheduled-workouts",
        input_schema_override=_GARMIN_SCHEDULED_WORKOUTS_SCHEMA,
    ),
]


TRAINING_PLAN_TOOLS_BY_NAME: dict[str, ToolDef] = {
    d.name: d for d in TRAINING_PLAN_TOOLS
}
