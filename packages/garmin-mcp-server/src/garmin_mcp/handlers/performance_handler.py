"""Handler for performance tools: get_performance_trends, get_weather_data, prefetch_activity_context."""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.utils.error_handling import safe_tool_handler


class PerformanceHandler:
    """Handles performance-related tool calls."""

    _tool_names: set[str] = {
        "get_performance_trends",
        "get_weather_data",
        "prefetch_activity_context",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    @safe_tool_handler
    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        activity_id = arguments["activity_id"]

        if name == "get_performance_trends":
            result = self._db_reader.get_performance_trends(activity_id)  # type: ignore[assignment]
        elif name == "get_weather_data":
            result = self._db_reader.get_weather_data(activity_id)  # type: ignore[assignment]
        elif name == "prefetch_activity_context":
            result = self._prefetch_activity_context(activity_id)  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=format_json_response(result))]

    @staticmethod
    def _prefetch_activity_context(activity_id: int) -> dict:
        """Delegate to the prefetch script function."""
        from garmin_mcp.scripts.prefetch_activity_context import (
            prefetch_activity_context,
        )

        return prefetch_activity_context(activity_id)
