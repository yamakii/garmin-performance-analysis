"""
JSON Utils MCP Server

Provides safe JSON read/write operations for LLM agents.
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
mcp = Server("json-utils")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available JSON utility tools."""
    return [
        Tool(
            name="json_read",
            description="Read JSON file with encoding auto-detection",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="json_write",
            description="Write JSON file atomically (temp → rename)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "data": {"type": "object"},
                    "indent": {"type": "integer", "default": 2},
                },
                "required": ["file_path", "data"],
            },
        ),
        Tool(
            name="json_validate",
            description="Validate JSON file integrity",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="json_get",
            description="Get nested value using dot notation",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "key_path": {"type": "string"},
                },
                "required": ["file_path", "key_path"],
            },
        ),
        Tool(
            name="json_update",
            description="Update JSON file (shallow or deep merge)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "updates": {"type": "object"},
                    "merge_mode": {"type": "string", "default": "shallow"},
                },
                "required": ["file_path", "updates"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    if name == "json_read":
        file_path = Path(arguments["file_path"])
        encoding = arguments.get("encoding", "utf-8")

        try:
            with open(file_path, encoding=encoding) as f:
                data = json.load(f)
            return [
                TextContent(
                    type="text", text=json.dumps(data, indent=2, ensure_ascii=False)
                )
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "json_write":
        file_path = Path(arguments["file_path"])
        data = arguments["data"]
        indent = arguments.get("indent", 2)

        try:
            # Atomic write: temp file → rename
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            temp_path.rename(file_path)

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": True, "path": str(file_path)}, indent=2
                    ),
                )
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "json_validate":
        file_path = Path(arguments["file_path"])

        try:
            with open(file_path, encoding="utf-8") as f:
                json.load(f)
            return [
                TextContent(type="text", text=json.dumps({"valid": True}, indent=2))
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"valid": False, "error": str(e)}, indent=2),
                )
            ]

    elif name == "json_get":
        file_path = Path(arguments["file_path"])
        key_path = arguments["key_path"]

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            # Navigate nested keys
            keys = key_path.split(".")
            value = data
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)]
                else:
                    value = None
                    break

            return [
                TextContent(
                    type="text", text=json.dumps(value, indent=2, ensure_ascii=False)
                )
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "json_update":
        file_path = Path(arguments["file_path"])
        updates = arguments["updates"]
        merge_mode = arguments.get("merge_mode", "shallow")

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            if merge_mode == "shallow":
                data.update(updates)
            else:  # deep merge

                def deep_merge(d: dict[str, Any], u: dict[str, Any]) -> dict[str, Any]:
                    for k, v in u.items():
                        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                            d[k] = deep_merge(d[k], v)
                        else:
                            d[k] = v
                    return d

                data = deep_merge(data, updates)

            # Atomic write
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.rename(file_path)

            return [
                TextContent(type="text", text=json.dumps({"success": True}, indent=2))
            ]
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
