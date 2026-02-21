"""Handler for performance tools: get_performance_trends, get_weather_data."""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response


class PerformanceHandler:
    """Handles performance-related tool calls."""

    _tool_names: set[str] = {"get_performance_trends", "get_weather_data"}

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        activity_id = arguments["activity_id"]

        if name == "get_performance_trends":
            result = self._db_reader.get_performance_trends(activity_id)  # type: ignore[assignment]
        elif name == "get_weather_data":
            result = self._db_reader.get_weather_data(activity_id)  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=format_json_response(result))]
