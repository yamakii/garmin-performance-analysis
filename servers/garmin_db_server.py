"""
Garmin DB MCP Server

Provides efficient DuckDB access to performance data via MCP protocol.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tools.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)

# Initialize server
mcp = Server("garmin-db")
db_reader = GarminDBReader()


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available DuckDB query tools."""
    return [
        Tool(
            name="get_performance_section",
            description="Get specific section from performance data",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "section": {"type": "string"},
                },
                "required": ["activity_id", "section"],
            },
        ),
        Tool(
            name="get_section_analysis",
            description="Get section analysis data from DuckDB",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "section_type": {"type": "string"},
                },
                "required": ["activity_id", "section_type"],
            },
        ),
        Tool(
            name="get_activity_by_date",
            description="Get activity ID and metadata from date",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                },
                "required": ["date"],
            },
        ),
        Tool(
            name="get_date_by_activity_id",
            description="Get date and activity name from activity ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    import json

    if name == "get_performance_section":
        activity_id = arguments["activity_id"]
        section = arguments["section"]
        result = db_reader.get_performance_section(activity_id, section)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_section_analysis":
        activity_id = arguments["activity_id"]
        section_type = arguments["section_type"]
        result = db_reader.get_section_analysis(activity_id, section_type)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_activity_by_date":
        date = arguments["date"]
        from tools.planner.workflow_planner import WorkflowPlanner

        planner = WorkflowPlanner()

        try:
            # Get all activities for date
            activities = planner._get_activities_from_duckdb(date)

            if len(activities) == 0:
                # Try API
                activities = planner._get_activities_from_api(date)

            if len(activities) == 0:
                result = {
                    "success": False,
                    "error": f"No activities found for {date}",
                    "activities": [],
                }
            elif len(activities) == 1:
                result = {
                    "success": True,
                    "activity_id": activities[0]["activity_id"],
                    "activity_name": activities[0]["activity_name"],
                    "start_time": activities[0]["start_time"],
                    "distance_km": activities[0]["distance_km"],
                    "duration_seconds": activities[0]["duration_seconds"],
                }
            else:
                result = {
                    "success": False,
                    "error": f"Multiple activities found for {date}. Please specify activity_id.",
                    "activities": activities,
                }

        except Exception as e:
            result = {"success": False, "error": str(e), "activities": []}

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_date_by_activity_id":
        activity_id = arguments["activity_id"]
        date = db_reader.get_activity_date(activity_id)
        result = {"activity_id": activity_id, "date": date}
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
