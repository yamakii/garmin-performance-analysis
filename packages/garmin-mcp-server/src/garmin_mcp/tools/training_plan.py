"""Fitness / Garmin-calendar domain tool definitions.

Self-authored plan *creation* (save/get plan, upload/delete Garmin workouts) was
removed in #787. What remains are the two read-only tools that survive: the
current-fitness assessment (delegating to ``fitness/``) and the Garmin Connect
scheduled-workout calendar reader.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

# Runtime default preserved from the previous Pydantic model (the optional field
# below is modeled as ``... | None = None`` so the derived MCP schema emits no
# ``default`` key, matching the hand schema; the handler coalesces to this).
_DEFAULT_LOOKBACK_WEEKS = 8

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class CurrentFitnessSummaryParams(BaseModel):
    """Arguments for ``get_current_fitness_summary``."""

    lookback_weeks: int | None = Field(
        default=None, description="Number of weeks to analyze (default: 8)"
    )


class GarminScheduledWorkoutsParams(BaseModel):
    """Arguments for ``get_garmin_scheduled_workouts``."""

    start_date: str = Field(description="Inclusive start date (YYYY-MM-DD)")
    end_date: str = Field(description="Inclusive end date (YYYY-MM-DD)")


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _get_current_fitness_summary(
    reader: GarminDBReader, p: CurrentFitnessSummaryParams
) -> Any:
    from garmin_mcp.fitness.fitness_assessor import FitnessAssessor

    try:
        lookback = (
            p.lookback_weeks
            if p.lookback_weeks is not None
            else _DEFAULT_LOOKBACK_WEEKS
        )
        assessor = FitnessAssessor(db_path=str(reader.db_path))
        summary = assessor.assess(lookback_weeks=lookback)
        result = summary.model_dump()

        # Attach a body-composition summary (#501). Independent + null-safe: a
        # failure here must not break the fitness assessment, so it is best-effort
        # and surfaces nothing when body-composition data is absent.
        try:
            body_comp = reader.get_body_composition_trend(weeks=lookback)
            if body_comp.get("series"):
                result["body_composition"] = body_comp
        except Exception as bc_err:  # noqa: BLE001
            logger.warning(f"Body-composition summary skipped: {bc_err}")

        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fitness assessment failed: {e}")
        return {"error": str(e)}


def _get_garmin_scheduled_workouts(
    reader: GarminDBReader, p: GarminScheduledWorkoutsParams
) -> Any:
    from garmin_mcp.fitness.garmin_calendar import GarminCalendarReader

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
    ),
]


TRAINING_PLAN_TOOLS_BY_NAME: dict[str, ToolDef] = {
    d.name: d for d in TRAINING_PLAN_TOOLS
}
