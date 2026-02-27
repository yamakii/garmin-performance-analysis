"""
Garmin DB MCP Server

Provides efficient DuckDB access to performance data via MCP protocol.
"""

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.analysis_handler import AnalysisHandler
from garmin_mcp.handlers.base import ToolHandler
from garmin_mcp.handlers.export_handler import ExportHandler
from garmin_mcp.handlers.metadata_handler import MetadataHandler
from garmin_mcp.handlers.performance_handler import PerformanceHandler
from garmin_mcp.handlers.physiology_handler import PhysiologyHandler
from garmin_mcp.handlers.splits_handler import SplitsHandler
from garmin_mcp.handlers.time_series_handler import TimeSeriesHandler
from garmin_mcp.handlers.training_plan_handler import TrainingPlanHandler
from garmin_mcp.tool_schemas import get_tool_definitions

logger = logging.getLogger(__name__)

OVERRIDE_FILE = "/tmp/garmin-mcp-server-dir"

# Initialize server
mcp = Server("garmin-db")
db_reader = GarminDBReader()

# Registry of handlers (lazily initialized)
_handlers: list[ToolHandler] = []


def _init_handlers() -> None:
    """Initialize handler registry with db_reader instance."""
    global _handlers
    _handlers = [
        MetadataHandler(db_reader),
        SplitsHandler(db_reader),
        PhysiologyHandler(db_reader),
        PerformanceHandler(db_reader),
        AnalysisHandler(db_reader),
        TimeSeriesHandler(db_reader),
        ExportHandler(db_reader),
        TrainingPlanHandler(db_reader),
    ]


def _get_server_dir() -> str:
    """Get the package directory this server is running from."""
    return str(Path(__file__).resolve().parent.parent)


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available DuckDB query tools."""
    return get_tool_definitions()


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls by dispatching to the appropriate handler."""
    import time

    start = time.monotonic()
    try:
        result = await _dispatch_tool(name, arguments)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info("tool=%s duration_ms=%.1f status=ok", name, duration_ms)
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        logger.error(
            "tool=%s duration_ms=%.1f status=error error=%s", name, duration_ms, e
        )
        raise


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool call to the appropriate handler."""
    if name == "reload_server":
        return await _handle_reload_server(server_dir=arguments.get("server_dir"))
    if name == "get_server_info":
        return _handle_get_server_info()
    if not _handlers:
        _init_handlers()
    for handler in _handlers:
        if handler.handles(name):
            return await handler.handle(name, arguments)
    raise ValueError(f"Unknown tool: {name}")


def _handle_get_server_info() -> list[TextContent]:
    """Return diagnostic info about the running server."""
    server_dir = _get_server_dir()
    override_exists = os.path.exists(OVERRIDE_FILE)
    override_dir: str | None = None
    if override_exists:
        try:
            with open(OVERRIDE_FILE) as f:
                override_dir = f.read().strip()
        except OSError:
            pass

    info: dict[str, Any] = {
        "server_dir": server_dir,
        "override_file_exists": override_exists,
        "override_dir": override_dir,
    }

    # DB diagnostics (best-effort, never raise)
    try:
        from garmin_mcp.database.connection import get_connection

        with get_connection() as conn:
            tables = conn.execute("SHOW TABLES").fetchall()
            info["db_status"] = "connected"
            info["table_count"] = len(tables)
            row = conn.execute(
                "SELECT MAX(start_time_local) FROM activities"
            ).fetchone()
            info["last_ingest_date"] = str(row[0]) if row and row[0] else None
    except Exception as e:
        info["db_status"] = f"error: {e}"
        info["table_count"] = None
        info["last_ingest_date"] = None

    # Tool count
    info["tool_count"] = len(get_tool_definitions())

    return [TextContent(type="text", text=json.dumps(info))]


def _graceful_shutdown() -> None:
    """Perform cleanup and exit gracefully.

    Uses os._exit(0) instead of sys.exit() because sys.exit() raises SystemExit,
    which may be caught and suppressed by the asyncio event loop when called from
    loop.call_later(). os._exit(0) guarantees process termination. The graceful
    aspect is running cleanup *before* the hard exit.
    """
    logger.info("Graceful shutdown initiated")
    try:
        from garmin_mcp.mcp_server.export_manager import get_export_manager

        get_export_manager().cleanup_all()
    except Exception:
        logger.debug("Export cleanup skipped (not initialized)")
    try:
        from garmin_mcp.mcp_server.view_manager import get_view_manager

        get_view_manager().cleanup_all()
    except Exception:
        logger.debug("View cleanup skipped (not initialized)")
    logger.info("Cleanup complete, exiting")
    os._exit(0)


async def _handle_reload_server(
    server_dir: str | None = None,
) -> list[TextContent]:
    """Handle reload_server by scheduling process exit after response is sent.

    If server_dir is provided, validates the directory contains pyproject.toml,
    then writes it to /tmp/garmin-mcp-server-dir so the launcher script starts
    from that directory on reconnect.
    If server_dir is not provided, removes the override file to restore default.
    """
    if server_dir is not None:
        pyproject = os.path.join(server_dir, "pyproject.toml")
        if not os.path.isdir(server_dir) or not os.path.isfile(pyproject):
            error_resp = json.dumps(
                {
                    "success": False,
                    "error": f"Invalid server_dir: '{server_dir}' "
                    f"(directory or pyproject.toml not found)",
                }
            )
            return [TextContent(type="text", text=error_resp)]

        with open(OVERRIDE_FILE, "w") as f:
            f.write(server_dir)
        msg = f"Server will restart from: {server_dir}"
        logger.info("reload_server called with server_dir=%s", server_dir)
    else:
        if os.path.exists(OVERRIDE_FILE):
            os.remove(OVERRIDE_FILE)
        msg = "Server will restart from default directory."
        logger.info("reload_server called - restoring default directory")

    loop = asyncio.get_event_loop()
    loop.call_later(0.5, _graceful_shutdown)
    return [
        TextContent(
            type="text",
            text=json.dumps({"success": True, "message": msg}),
        )
    ]


async def main() -> None:
    """Main entry point for MCP server."""
    from garmin_mcp.utils.logging_config import setup_mcp_logging

    setup_mcp_logging()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, _graceful_shutdown)
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def run() -> None:
    """Console script entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
