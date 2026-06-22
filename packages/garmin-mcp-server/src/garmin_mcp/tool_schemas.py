"""Tool schema definitions for the Garmin DB MCP Server.

All handler-domain tools are now declared via the single-source registry
(``garmin_mcp.tools.ALL_DEFS``) and built with ``build_mcp_tools``. This module
no longer hand-declares any handler tool; it only retains the two server-level
tools (``get_server_info``, ``reload_server``) that are handled directly in
``server.py`` rather than by a domain handler.

``get_tool_definitions()`` returns ``build_mcp_tools(ALL_DEFS)`` followed by the
server tools, preserving the exact 41-tool order the MCP surface served before
the registry rollout.
"""

from mcp.types import Tool

from garmin_mcp.tools import ALL_DEFS
from garmin_mcp.tools.registry import build_mcp_tools

# Server-level tools are dispatched directly in server.py (not via a domain
# handler), so they remain hand-declared here and are appended last.
_SERVER_TOOLS: list[dict] = [
    {
        "name": "get_server_info",
        "description": "Get diagnostic info about the running MCP server (server_dir). Use to verify which directory the server is running from.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "reload_server",
        "description": "Restart the worker to pick up the latest code. The launcher process stays alive, so the MCP connection is preserved (no reconnect needed).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _hand_schema_to_tool(schema: dict) -> Tool:
    return Tool(
        name=schema["name"],
        description=schema["description"],
        inputSchema=schema["inputSchema"],
    )


def get_tool_definitions() -> list[Tool]:
    """Return all MCP tool definitions as a list of Tool objects.

    All handler-domain tools come from the single-source registry
    (``build_mcp_tools(ALL_DEFS)``); the two server-level tools are appended
    afterwards. Ordering is byte-for-byte identical to the pre-registry surface.
    """
    return build_mcp_tools(ALL_DEFS) + [_hand_schema_to_tool(s) for s in _SERVER_TOOLS]


# Tool name registry for validation.
TOOL_NAMES: set[str] = {d.name for d in ALL_DEFS} | {
    schema["name"] for schema in _SERVER_TOOLS
}
