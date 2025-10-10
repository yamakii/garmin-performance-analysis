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
        Tool(
            name="get_splits_pace_hr",
            description="Get pace and heart rate data from splits (lightweight: ~3 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_form_metrics",
            description="Get form efficiency metrics from splits (lightweight: ~4 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_elevation",
            description="Get elevation and terrain data from splits (lightweight: ~5 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="insert_section_analysis_dict",
            description="Insert section analysis dict directly into DuckDB (no file creation)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "activity_date": {"type": "string"},
                    "section_type": {"type": "string"},
                    "analysis_data": {"type": "object"},
                },
                "required": [
                    "activity_id",
                    "activity_date",
                    "section_type",
                    "analysis_data",
                ],
            },
        ),
        Tool(
            name="get_form_efficiency_summary",
            description="Get form efficiency summary (GCT, VO, VR metrics) from form_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_hr_efficiency_analysis",
            description="Get HR efficiency analysis (zone distribution, training type) from hr_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_heart_rate_zones_detail",
            description="Get heart rate zones detail (boundaries, time distribution) from heart_rate_zones table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_vo2_max_data",
            description="Get VO2 max data (precise value, fitness age, category) from vo2_max table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_lactate_threshold_data",
            description="Get lactate threshold data (HR, speed, power) from lactate_threshold table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_all",
            description="Get all split data (all 22 fields) from splits table",
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
        import duckdb

        try:
            # Query activities table for given date
            conn = duckdb.connect(str(db_reader.db_path), read_only=True)
            activities_result = conn.execute(
                """
                SELECT
                    activity_id,
                    activity_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds
                FROM activities
                WHERE date = ?
                ORDER BY start_time_local
                """,
                [date],
            ).fetchall()
            conn.close()

            activities = [
                {
                    "activity_id": row[0],
                    "activity_name": row[1],
                    "start_time": str(row[2]) if row[2] else None,
                    "distance_km": row[3],
                    "duration_seconds": row[4],
                }
                for row in activities_result
            ]

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

    elif name == "get_splits_pace_hr":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_pace_hr(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_form_metrics":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_form_metrics(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_elevation":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_elevation(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "insert_section_analysis_dict":
        from tools.database.inserters.section_analyses import insert_section_analysis

        activity_id = arguments["activity_id"]
        activity_date = arguments["activity_date"]
        section_type = arguments["section_type"]
        analysis_data = arguments["analysis_data"]

        success = insert_section_analysis(
            activity_id=activity_id,
            activity_date=activity_date,
            section_type=section_type,
            analysis_data=analysis_data,
        )

        result = {
            "success": success,
            "activity_id": activity_id,
            "section_type": section_type,
        }

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_form_efficiency_summary":
        activity_id = arguments["activity_id"]
        result = db_reader.get_form_efficiency_summary(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_hr_efficiency_analysis":
        activity_id = arguments["activity_id"]
        result = db_reader.get_hr_efficiency_analysis(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_heart_rate_zones_detail":
        activity_id = arguments["activity_id"]
        result = db_reader.get_heart_rate_zones_detail(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_vo2_max_data":
        activity_id = arguments["activity_id"]
        result = db_reader.get_vo2_max_data(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_lactate_threshold_data":
        activity_id = arguments["activity_id"]
        result = db_reader.get_lactate_threshold_data(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_all":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_all(activity_id)
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
