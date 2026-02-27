"""Handler for splits tools."""

import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.utils.error_handling import safe_tool_handler

logger = logging.getLogger(__name__)


class SplitsHandler:
    """Handles splits-related tool calls."""

    _tool_names: set[str] = {
        "get_splits_pace_hr",
        "get_splits_form_metrics",
        "get_splits_elevation",
        "get_splits_comprehensive",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    @safe_tool_handler
    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        activity_id = arguments["activity_id"]

        if name == "get_splits_pace_hr":
            statistics_only = arguments.get("statistics_only", False)
            result = self._db_reader.get_splits_pace_hr(
                activity_id, statistics_only=statistics_only
            )
        elif name == "get_splits_form_metrics":
            statistics_only = arguments.get("statistics_only", False)
            result = self._db_reader.get_splits_form_metrics(
                activity_id, statistics_only=statistics_only
            )
        elif name == "get_splits_elevation":
            statistics_only = arguments.get("statistics_only", False)
            result = self._db_reader.get_splits_elevation(
                activity_id, statistics_only=statistics_only
            )
        elif name == "get_splits_comprehensive":
            statistics_only = arguments.get("statistics_only", False)
            result = self._db_reader.get_splits_comprehensive(
                activity_id, statistics_only=statistics_only
            )
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=format_json_response(result))]
