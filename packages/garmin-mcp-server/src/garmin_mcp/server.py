"""Garmin DB MCP Server — stable shim.

This module is a tiny, *unchanging* shim that owns the MCP protocol session and
nothing else. All volatile domain code (tool registry, DB readers) lives in the
swappable :mod:`garmin_mcp.worker`, which the shim drives through a single
:class:`~garmin_mcp.worker_client.WorkerClient`.

Responsibilities:

- ``list_tools`` -- domain tools from ``worker.rpc("schema")`` + the two
  server-level tools (``get_server_info``, ``reload_server``).
- ``call_tool``  -- ``get_server_info``/``reload_server`` handled inline; every
  other tool is delegated to ``worker.rpc("call", name, args)``.
- ``reload_server`` -- ``worker.restart()`` (fresh process = latest on-disk
  code) followed by ``notifications/tools/list_changed``. There is **no**
  ``os._exit`` / client-respawn dependency: the shim process stays alive, so the
  MCP session (and subagent tool access) survives a reload.

Because the shim never imports the volatile ``garmin_mcp.tools`` / ``database``
modules, its schema and behaviour stay stable across code edits — only the
worker changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import UTC, datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from garmin_mcp.worker_client import WorkerClient

logger = logging.getLogger(__name__)

# Process start time, recorded once at module load (ISO 8601, UTC). Callers use
# this to confirm the *shim* identity; a reload must NOT change it (only the
# worker is replaced).
_STARTED_AT: str = datetime.now(UTC).isoformat()

# The two server-level tools are owned by the shim, not the worker. They are
# appended to the worker's domain-tool schema in ``list_tools``.
_SERVER_TOOLS: list[Tool] = [
    Tool(
        name="get_server_info",
        description=(
            "Get diagnostic info about the running MCP server (shim started_at "
            "plus worker DB diagnostics). Use to verify readiness."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="reload_server",
        description=(
            "Restart the execution worker to pick up code changes. The MCP shim "
            "process stays alive (the session is preserved) and a "
            "tools/list_changed notification is sent. Signature-compatible "
            "changes apply with no reconnect; schema changes (added/removed "
            "tools or changed args) need one /mcp reconnect."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
]
_SERVER_TOOL_NAMES = {t.name for t in _SERVER_TOOLS}


# Initialize server + the single worker the shim delegates to.
mcp: Server = Server("garmin-db")
worker = WorkerClient()


def _extract_log_context(arguments: dict[str, Any]) -> str:
    """Extract activity_id or date from arguments for log context."""
    if "activity_id" in arguments:
        return f"activity_id={arguments['activity_id']} "
    if "date" in arguments:
        return f"date={arguments['date']} "
    return ""


def _detect_tool_error(result: list) -> bool:
    """Check if any TextContent in result contains an error response."""
    for item in result:
        if hasattr(item, "text"):
            try:
                data = json.loads(item.text)
                if isinstance(data, dict) and "error" in data:
                    return True
            except (ValueError, TypeError):
                pass
    return False


def _count_warnings(result: list) -> int:
    """Count warnings in tool result."""
    for item in result:
        if hasattr(item, "text"):
            try:
                data = json.loads(item.text)
                if isinstance(data, dict) and "_warnings" in data:
                    return len(data["_warnings"])
            except (ValueError, TypeError):
                pass
    return 0


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools: worker-provided domain tools + 2 server tools.

    The domain schema comes from the worker (so it always reflects the latest
    on-disk registry); the two server tools are appended by the shim.
    """
    resp = await worker.rpc("schema")
    domain_tools: list[Tool] = []
    if resp.get("ok"):
        for spec in resp.get("data", []):
            domain_tools.append(
                Tool(
                    name=spec["name"],
                    description=spec.get("description", ""),
                    inputSchema=spec.get("inputSchema", {"type": "object"}),
                )
            )
    else:
        logger.error("worker schema failed: %s", resp.get("error"))
    return domain_tools + _SERVER_TOOLS


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle a tool call by dispatching to the shim handler or the worker."""
    import time

    start = time.monotonic()
    try:
        result = await _dispatch_tool(name, arguments)
        duration_ms = (time.monotonic() - start) * 1000
        ctx = _extract_log_context(arguments)
        if _detect_tool_error(result):
            logger.warning(
                "tool=%s %sduration_ms=%.1f status=tool_error",
                name,
                ctx,
                duration_ms,
            )
        else:
            logger.info("tool=%s %sduration_ms=%.1f status=ok", name, ctx, duration_ms)
        warning_count = _count_warnings(result)
        if warning_count > 0:
            logger.info("tool=%s %swarning_count=%d", name, ctx, warning_count)
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        logger.error(
            "tool=%s duration_ms=%.1f status=error error=%s", name, duration_ms, e
        )
        raise


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route a tool call: server tools inline, everything else to the worker.

    Domain tools are delegated to ``worker.rpc("call", ...)``; the result (or a
    structured error) is serialized into a single ``TextContent``. The shim does
    not import the registry, so unknown names are surfaced by the worker as an
    ``ok=False`` error rather than raised here.
    """
    if name == "reload_server":
        return await _handle_reload_server()
    if name == "get_server_info":
        return await _handle_get_server_info()

    resp = await worker.rpc("call", name, arguments)
    if resp.get("ok"):
        payload = resp.get("data")
    else:
        payload = {"error": resp.get("error", "worker call failed")}
    return [TextContent(type="text", text=json.dumps(payload, default=str))]


async def _handle_get_server_info() -> list[TextContent]:
    """Compose shim identity (started_at) with worker DB diagnostics.

    The worker reports DB diagnostics (``table_count``, ``last_ingest_date``) via
    ``rpc("info")``; the shim adds its own ``started_at`` and a ``ready`` flag so
    callers can confirm the worker answered.
    """
    info: dict[str, Any] = {
        "started_at": _STARTED_AT,
        "ready": False,
    }
    resp = await worker.rpc("info")
    if resp.get("ok"):
        worker_info = resp.get("data", {})
        info["ready"] = True
        info["db_status"] = "connected" if "db_error" not in worker_info else "error"
        info["db_path"] = worker_info.get("db_path")
        info["worker_started_at"] = worker_info.get("started_at")
        info["table_count"] = worker_info.get("table_count")
        info["last_ingest_date"] = worker_info.get("last_ingest_date")
        if "db_error" in worker_info:
            info["db_error"] = worker_info["db_error"]
    else:
        info["db_status"] = f"error: {resp.get('error')}"
        info["table_count"] = None
        info["last_ingest_date"] = None

    return [TextContent(type="text", text=json.dumps(info, default=str))]


async def _handle_reload_server() -> list[TextContent]:
    """Swap the worker for a fresh process and notify clients of tool changes.

    No process suicide: the shim restarts only the worker (latest on-disk code)
    then sends ``notifications/tools/list_changed`` so connected clients refetch
    the tool list. The shim PID is unchanged, so the MCP session is preserved.
    """
    await worker.restart()

    notified = False
    try:
        await mcp.request_context.session.send_tool_list_changed()
        notified = True
    except LookupError:
        # No active request context (e.g. called outside a live session): the
        # restart still succeeded, we just can't push a notification.
        logger.debug("reload_server: no request context, skipping list_changed")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reload_server: send_tool_list_changed failed: %s", e)

    msg = (
        "Worker restarted with the latest on-disk code. The shim process is "
        "unchanged (session preserved). Signature-compatible changes are live "
        "now; schema changes need one /mcp reconnect."
    )
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {"success": True, "message": msg, "list_changed_sent": notified}
            ),
        )
    ]


async def main() -> None:
    """Main entry point for the MCP shim."""
    from garmin_mcp.utils.logging_config import setup_mcp_logging

    setup_mcp_logging()

    await worker.start()

    loop = asyncio.get_event_loop()

    def _on_term() -> None:
        # Terminate the worker, then stop serving. The shim has no DB/export
        # state of its own; cleanup lives in the worker (SIGTERM handler there).
        asyncio.ensure_future(worker.aclose())
        raise KeyboardInterrupt

    try:
        loop.add_signal_handler(signal.SIGTERM, _on_term)
    except (NotImplementedError, RuntimeError):  # pragma: no cover - platform dep
        pass

    try:
        async with stdio_server() as (read_stream, write_stream):
            await mcp.run(
                read_stream, write_stream, mcp.create_initialization_options()
            )
    finally:
        await worker.aclose()


def run() -> None:
    """Console script entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
