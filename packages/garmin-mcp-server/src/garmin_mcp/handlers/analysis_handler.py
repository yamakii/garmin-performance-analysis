"""Handler for analysis tools.

Thin adapter over the single-source registry
(``garmin_mcp.tools.analysis.ANALYSIS_TOOLS``). ``default=str`` is applied when
serializing so that date-bearing results (e.g. workout comparisons, insights)
remain JSON-encodable, matching the previous behavior.
"""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.analysis import ANALYSIS_TOOLS_BY_NAME
from garmin_mcp.tools.registry import dispatch
from garmin_mcp.utils.error_handling import safe_tool_handler


class AnalysisHandler:
    """Handles analysis-related tool calls via the registry."""

    _tool_names: set[str] = set(ANALYSIS_TOOLS_BY_NAME)

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    @safe_tool_handler
    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in self._tool_names:
            raise ValueError(f"Unknown tool: {name}")
        result = dispatch(ALL_DEFS_BY_NAME, self._db_reader, name, arguments)
        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]
