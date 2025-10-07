"""
Report Generator MCP Server

Jinja2テンプレートベースでレポート構造を生成し、
LLMが洞察のみを追加する効率的なレポート生成システム。
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# Initialize server
mcp = Server("report-generator")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available report generator tools."""
    return [
        Tool(
            name="create_report_structure",
            description="Create report structure from template",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["activity_id", "date"],
            },
        ),
        Tool(
            name="finalize_report",
            description="Finalize and save report to final destination",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "string"},
                    "date": {"type": "string"},
                    "temp_file_path": {"type": "string"},
                },
                "required": ["activity_id", "date", "temp_file_path"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    if name == "create_report_structure":
        activity_id = arguments["activity_id"]
        date = arguments["date"]

        # Generate template structure with 13 placeholders
        template = f"""# Running Performance Analysis - Activity {activity_id}

## Basic Information
- **Activity ID**: {activity_id}
- **Date**: {date}
- **Activity Type**: <!-- LLM_INSIGHTS_ACTIVITY_TYPE -->
- **Overall Rating**: <!-- LLM_INSIGHTS_OVERALL_RATING -->

## Performance Summary

### Key Strengths
<!-- LLM_INSIGHTS_STRENGTHS -->

### Areas for Improvement
<!-- LLM_INSIGHTS_IMPROVEMENTS -->

## Phase Analysis

### Warmup Phase
<!-- LLM_INSIGHTS_WARMUP -->

### Main Phase
<!-- LLM_INSIGHTS_MAIN -->

### Finish Phase
<!-- LLM_INSIGHTS_FINISH -->

## Efficiency Analysis

### Form Efficiency
<!-- LLM_INSIGHTS_FORM_EFFICIENCY -->

### HR Efficiency
<!-- LLM_INSIGHTS_HR_EFFICIENCY -->

## Environmental Factors

### Weather Conditions
<!-- LLM_INSIGHTS_WEATHER -->

### Terrain Impact
<!-- LLM_INSIGHTS_TERRAIN -->

## Split-by-Split Analysis
<!-- LLM_INSIGHTS_SPLITS -->

## Recommendations
<!-- LLM_INSIGHTS_RECOMMENDATIONS -->

---
*Generated with Garmin Performance Analysis System*
"""

        return [TextContent(type="text", text=template)]

    elif name == "finalize_report":
        activity_id = arguments["activity_id"]
        date = arguments["date"]
        temp_file_path = arguments["temp_file_path"]

        try:
            # Parse date to get year and month
            year, month, _ = date.split("-")

            # Create final destination path
            final_dir = project_root / "result" / "individual" / year / month
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / f"{date}_activity_{activity_id}.md"

            # Move temp file to final destination
            temp_path = Path(temp_file_path)
            if temp_path.exists():
                temp_path.rename(final_path)
            else:
                raise FileNotFoundError(f"Temp file not found: {temp_file_path}")

            result = {
                "success": True,
                "final_path": str(final_path),
                "message": f"Report saved to {final_path}",
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
