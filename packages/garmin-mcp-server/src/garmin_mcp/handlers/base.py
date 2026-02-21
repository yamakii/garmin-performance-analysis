"""Base protocol for tool handlers."""

import json
from collections.abc import Callable
from typing import Any, Protocol

from mcp.types import TextContent


def format_json_response(data: Any, *, default: Callable | None = None) -> str:
    """Format data as compact JSON for MCP responses."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=default)


class ToolHandler(Protocol):
    """Protocol for MCP tool handlers."""

    def handles(self, name: str) -> bool:
        """Return True if this handler handles the given tool name."""
        ...

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle a tool call and return results."""
        ...
