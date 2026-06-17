"""Handler for training-plan tools.

Thin adapter over the single-source registry
(``garmin_mcp.tools.training_plan.TRAINING_PLAN_TOOLS``). ``default=str`` is
applied when serializing so that date-bearing plan/workout payloads remain
JSON-encodable, matching the previous behavior.
"""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch
from garmin_mcp.tools.training_plan import TRAINING_PLAN_TOOLS_BY_NAME


class TrainingPlanHandler:
    """Handles training-plan-related tool calls via the registry."""

    _tool_names: set[str] = set(TRAINING_PLAN_TOOLS_BY_NAME)

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

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
