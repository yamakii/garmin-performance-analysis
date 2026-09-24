"""The two server-level tools owned by the shim.

``get_server_info`` and ``reload_server`` are dispatched in ``server.py``, not by
a domain handler. They live here, depending on ``mcp.types`` only, so the shim
can import them without loading worker code, and ``tool_schemas`` (the source
of the tool reference docs) serves the same text.
"""

from mcp.types import Tool

SERVER_TOOLS: list[Tool] = [
    Tool(
        name="get_server_info",
        description=(
            "Get diagnostic info about the running MCP server (shim started_at "
            "plus worker DB diagnostics). Use to verify readiness."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    Tool(
        name="reload_server",
        description=(
            "Restart the execution worker to pick up code changes. The MCP shim "
            "process stays alive (the session is preserved) and a "
            "tools/list_changed notification is sent. Signature-compatible "
            "changes apply with no reconnect; schema changes (added/removed "
            "tools or changed args) need one /mcp reconnect. Shim code "
            "(server.py, worker_client.py) is not reloaded and needs /mcp or a "
            "new session. The worker is pinned to the caller's working "
            "directory, so reload from the main checkout, not from a worktree "
            "that will be deleted. A subagent that calls it loses its garmin-db "
            "tools."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
]
