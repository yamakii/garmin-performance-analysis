"""Handler for metadata tools: get_activity_by_date, get_date_by_activity_id, ingest_activity."""

import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response

logger = logging.getLogger(__name__)


class MetadataHandler:
    """Handles metadata-related tool calls."""

    _tool_names: set[str] = {
        "get_activity_by_date",
        "get_date_by_activity_id",
        "ingest_activity",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_activity_by_date":
            return await self._get_activity_by_date(arguments)
        elif name == "get_date_by_activity_id":
            return await self._get_date_by_activity_id(arguments)
        elif name == "ingest_activity":
            return await self._ingest_activity(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def _get_activity_by_date(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.database.connection import get_connection

        date = arguments["date"]

        try:
            with get_connection(self._db_reader.db_path) as conn:
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

        except Exception as e:
            result = {"success": False, "error": str(e), "activities": []}

        return [TextContent(type="text", text=format_json_response(result))]

    async def _get_date_by_activity_id(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        activity_id = arguments["activity_id"]
        date = self._db_reader.get_activity_date(activity_id)
        result = {"activity_id": activity_id, "date": date}
        return [TextContent(type="text", text=format_json_response(result))]

    async def _ingest_activity(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.planner.workflow_planner import WorkflowPlanner

        date = arguments["date"]
        force_regenerate = arguments.get("force_regenerate", False)

        try:
            planner = WorkflowPlanner(db_path=str(self._db_reader.db_path))
            workflow_result = planner.execute_full_workflow(
                date=date, force_regenerate=force_regenerate
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
        except Exception as e:
            logger.error(f"Ingest activity failed for {date}: {e}", exc_info=True)
            result = {"success": False, "error": str(e)}

        return [TextContent(type="text", text=format_json_response(result))]
