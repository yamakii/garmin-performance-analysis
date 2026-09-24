"""Metadata domain tool definitions."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.analysis.derivations import format_gear_label
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetActivityByDateParams(BaseModel):
    """Arguments for ``get_activity_by_date``."""

    date: str = Field(description="Local calendar date of the run, YYYY-MM-DD")


class GetDateByActivityIdParams(BaseModel):
    """Arguments for ``get_date_by_activity_id``."""

    activity_id: int = Field(description="Garmin activity ID to look up")


class IngestActivityParams(BaseModel):
    """Arguments for ``ingest_activity``."""

    date: str = Field(description="Activity date in YYYY-MM-DD format")


def _get_activity_by_date(
    reader: GarminDBReader, p: GetActivityByDateParams
) -> dict[str, Any]:
    from garmin_mcp.database.connection import get_connection

    date = p.date
    try:
        with get_connection(reader.db_path) as conn:
            activities_result = conn.execute(
                """
                SELECT
                    activity_id,
                    activity_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds,
                    gear_type,
                    gear_model,
                    gear_nickname
                FROM activities
                WHERE activity_date = ?
                ORDER BY start_time_local
                """,
                [date],
            ).fetchall()

        activities = [
            {
                "activity_id": row[0],
                "activity_name": row[1],
                "start_time": str(row[2]) if row[2] else None,
                "distance_km": row[3],
                "duration_seconds": row[4],
                "gear_type": row[5],
                "gear_model": row[6],
                "gear_nickname": row[7],
                "gear_label": format_gear_label(row[6], row[7]),
            }
            for row in activities_result
        ]

        if len(activities) == 0:
            result: dict[str, Any] = {
                "success": False,
                "error": f"No activities found for {date}",
                "activities": [],
            }
        elif len(activities) == 1:
            result = {
                "success": True,
                "activity_id": activities[0]["activity_id"],
                "activity_name": activities[0]["activity_name"],
                "start_time": activities[0]["start_time"],
                "distance_km": activities[0]["distance_km"],
                "duration_seconds": activities[0]["duration_seconds"],
                "gear_type": activities[0]["gear_type"],
                "gear_model": activities[0]["gear_model"],
                "gear_nickname": activities[0]["gear_nickname"],
                "gear_label": activities[0]["gear_label"],
            }
        else:
            result = {
                "success": False,
                "error": (
                    f"Multiple activities found for {date}. "
                    "Pick one from activities."
                ),
                "activities": activities,
            }
    except Exception as e:  # noqa: BLE001
        result = {"success": False, "error": str(e), "activities": []}

    return result


def _get_date_by_activity_id(
    reader: GarminDBReader, p: GetDateByActivityIdParams
) -> dict[str, Any]:
    date = reader.get_activity_date(p.activity_id)
    return {"activity_id": p.activity_id, "date": date}


def _ingest_activity(reader: GarminDBReader, p: IngestActivityParams) -> dict[str, Any]:
    from garmin_mcp.planner.workflow_planner import WorkflowPlanner

    try:
        planner = WorkflowPlanner(db_path=str(reader.db_path))
        workflow_result = planner.execute_full_workflow(date=p.date)
        result: dict[str, Any] = {
            "success": True,
            "activity_id": workflow_result["activity_id"],
            "date": str(workflow_result["date"]),
            "form_evaluation_status": workflow_result.get(
                "form_evaluation_status", "unknown"
            ),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ingest activity failed for {p.date}: {e}", exc_info=True)
        result = {"success": False, "error": str(e)}

    return result


METADATA_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_activity_by_date",
        description=(
            "Resolve a local date to the ingested run(s) on that day. With exactly "
            "one run, returns success=true plus activity_id, activity_name, "
            "start_time (local), distance_km, duration_seconds and gear "
            "(gear_type, gear_model, gear_nickname, gear_label). With none or "
            "several, returns success=false, an error and an activities list with "
            "the same fields to pick from. Only runs already ingested into DuckDB "
            "are found; ingest_activity fetches a new day."
        ),
        params=GetActivityByDateParams,
        handler=_get_activity_by_date,
        cli_group="metadata",
        cli_name="activity-by-date",
    ),
    ToolDef(
        name="get_date_by_activity_id",
        description=(
            "Look up the local activity date of an ingested activity. Returns "
            "{activity_id, date} with date as YYYY-MM-DD, or date=null when the ID "
            "is not in DuckDB. It returns no name, distance or metrics; "
            "get_activity_by_date gives those for a date."
        ),
        params=GetDateByActivityIdParams,
        handler=_get_date_by_activity_id,
        cli_group="metadata",
        cli_name="date-by-activity-id",
    ),
    ToolDef(
        name="ingest_activity",
        description=(
            "Ingest the one run on date from Garmin Connect (raw files are "
            "cache-first), write it to DuckDB and run the pace-corrected form "
            "evaluation. Returns {success: true, activity_id, date, "
            "form_evaluation_status} where form_evaluation_status is success, "
            "model_not_found, failed or error; returns {success: false, error} "
            "when the day has no run or several. Use catch_up_ingest for a date "
            "range and get_activity_by_date to read a run that is already "
            "ingested."
        ),
        params=IngestActivityParams,
        handler=_ingest_activity,
        cli_group="metadata",
        cli_name="ingest",
    ),
]


METADATA_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in METADATA_TOOLS}
