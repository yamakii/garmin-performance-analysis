"""Handler for physiology tools.

Thin adapter over the single-source registry: tool names and dispatch are
derived from ``garmin_mcp.tools.physiology.PHYSIOLOGY_TOOLS`` and routed through
the aggregate ``ALL_DEFS_BY_NAME`` lookup.
"""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.physiology import PHYSIOLOGY_TOOLS_BY_NAME
from garmin_mcp.tools.registry import dispatch


class PhysiologyHandler:
    """Handles physiology-related tool calls via the registry."""

    # Derived from the single-source registry (no hand-maintained duplicate).
    _tool_names: set[str] = set(PHYSIOLOGY_TOOLS_BY_NAME)

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in self._tool_names:
            raise ValueError(f"Unknown tool: {name}")
        result = dispatch(ALL_DEFS_BY_NAME, self._db_reader, name, arguments)
        return [TextContent(type="text", text=format_json_response(result))]
