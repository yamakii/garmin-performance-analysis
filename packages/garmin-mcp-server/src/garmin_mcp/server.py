"""
Garmin DB MCP Server

Provides efficient DuckDB access to performance data via MCP protocol.
"""

import asyncio
import logging
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


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available DuckDB query tools."""
    return get_tool_definitions()


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls by dispatching to the appropriate handler."""
    if not _handlers:
        _init_handlers()
    for handler in _handlers:
        if handler.handles(name):
            return await handler.handle(name, arguments)
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def run() -> None:
    """Console script entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
