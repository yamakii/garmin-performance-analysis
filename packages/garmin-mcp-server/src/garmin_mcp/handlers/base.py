"""Base protocol for tool handlers."""

from typing import Any, Protocol

from mcp.types import TextContent


class ToolHandler(Protocol):
    """Protocol for MCP tool handlers."""

    def handles(self, name: str) -> bool:
        """Return True if this handler handles the given tool name."""
        ...

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle a tool call and return results."""
        ...
