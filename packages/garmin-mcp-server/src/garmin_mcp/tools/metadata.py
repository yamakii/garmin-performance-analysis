"""Metadata domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetActivityByDateParams(BaseModel):
    """Arguments for ``get_activity_by_date``."""

    date: str = Field(description="Date in YYYY-MM-DD format")


class GetDateByActivityIdParams(BaseModel):
    """Arguments for ``get_date_by_activity_id``."""

    activity_id: int


class IngestActivityParams(BaseModel):
    """Arguments for ``ingest_activity``."""

    date: str = Field(description="Activity date in YYYY-MM-DD format")
    force_regenerate: bool = Field(
        default=False,
        description="Force regeneration of all data (default: false)",
    )


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
                    total_time_seconds
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
            }
        else:
            result = {
                "success": False,
                "error": f"Multiple activities found for {date}. Please specify activity_id.",
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
        workflow_result = planner.execute_full_workflow(
            date=p.date, force_regenerate=p.force_regenerate
        )
        result: dict[str, Any] = {
            "success": True,
            "activity_id": workflow_result["activity_id"],
            "date": str(workflow_result["date"]),
            "form_evaluation_status": workflow_result.get(
                "form_evaluation_status", "unknown"
            ),
            "validation_status": workflow_result.get("validation_status"),
            "quality_score": workflow_result.get("quality_score"),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ingest activity failed for {p.date}: {e}", exc_info=True)
        result = {"success": False, "error": str(e)}

    return result


METADATA_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_activity_by_date",
        description="Get activity ID and metadata from date",
        params=GetActivityByDateParams,
        handler=_get_activity_by_date,
        cli_group="metadata",
        cli_name="activity-by-date",
    ),
    ToolDef(
        name="get_date_by_activity_id",
        description="Get date and activity name from activity ID",
        params=GetDateByActivityIdParams,
        handler=_get_date_by_activity_id,
        cli_group="metadata",
        cli_name="date-by-activity-id",
    ),
    ToolDef(
        name="ingest_activity",
        description=(
            "Ingest activity data from Garmin Connect into DuckDB. Fetches raw "
            "data, stores in DuckDB, and runs form evaluation."
        ),
        params=IngestActivityParams,
        handler=_ingest_activity,
        cli_group="metadata",
        cli_name="ingest",
    ),
]


METADATA_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in METADATA_TOOLS}
