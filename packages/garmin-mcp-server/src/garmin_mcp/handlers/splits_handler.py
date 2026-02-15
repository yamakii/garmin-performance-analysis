"""Handler for splits tools."""

import json
import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.config import DEFAULT_MAX_OUTPUT_SIZE
from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class SplitsHandler:
    """Handles splits-related tool calls."""

    _tool_names: set[str] = {
        "get_splits_pace_hr",
        "get_splits_form_metrics",
        "get_splits_elevation",
        "get_splits_comprehensive",
        "get_splits_all",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

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
        elif name == "get_splits_all":
            logger.warning(
                "DEPRECATED: get_splits_all() is deprecated. "
                "Use get_splits_comprehensive() or export() instead."
            )
            max_output_size = arguments.get("max_output_size", DEFAULT_MAX_OUTPUT_SIZE)
            result = self._db_reader.get_splits_all(activity_id, max_output_size)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]
