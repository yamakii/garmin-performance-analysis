"""
Markdown Utils MCP Server

Provides safe Markdown read/write operations for LLM agents.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ContentBlock,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None = None
) -> ListToolsResult:
    """List available Markdown utility tools."""
    tools = [
        Tool(
            name="markdown_read",
            description="Read Markdown file with encoding auto-detection",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="markdown_write",
            description="Write Markdown file atomically",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        ),
        Tool(
            name="markdown_list_headings",
            description="List all headings with levels and line numbers",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="markdown_get_section",
            description="Extract specific section by heading",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "heading": {"type": "string"},
                    "include_subsections": {"type": "boolean", "default": True},
                },
                "required": ["file_path", "heading"],
            },
        ),
        Tool(
            name="markdown_update_section",
            description="Update specific section by heading",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "heading": {"type": "string"},
                    "new_content": {"type": "string"},
                    "include_subsections": {"type": "boolean", "default": True},
                },
                "required": ["file_path", "heading", "new_content"],
            },
        ),
        Tool(
            name="markdown_append",
            description="Append content to file",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        ),
    ]
    return ListToolsResult(tools=tools)


async def _dispatch(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Run the named tool and return its content blocks."""
    if name == "markdown_read":
        file_path = Path(arguments["file_path"])
        encoding = arguments.get("encoding", "utf-8")

        try:
            with open(file_path, encoding=encoding) as f:
                content = f.read()
            return [TextContent(type="text", text=content)]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "markdown_write":
        file_path = Path(arguments["file_path"])
        content = arguments["content"]

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
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

    elif name == "markdown_list_headings":
        file_path = Path(arguments["file_path"])

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            headings = []
            for i, line in enumerate(lines, 1):
                match = re.match(r"^(#{1,6})\s+(.+)$", line)
                if match:
                    level = len(match.group(1))
                    text = match.group(2).strip()
                    headings.append({"level": level, "text": text, "line": i})

            return [
                TextContent(
                    type="text", text=json.dumps(headings, indent=2, ensure_ascii=False)
                )
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "markdown_get_section":
        file_path = Path(arguments["file_path"])
        heading = arguments["heading"]
        include_subsections = arguments.get("include_subsections", True)

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Find section
            section_lines = []
            in_section = False
            section_level = 0

            for line in lines:
                match = re.match(r"^(#{1,6})\s+(.+)$", line)

                if (
                    match
                    and match.group(2).strip() == heading.strip().lstrip("#").strip()
                ):
                    in_section = True
                    section_level = len(match.group(1))
                    section_lines.append(line)
                elif in_section:
                    if match:
                        current_level = len(match.group(1))
                        if current_level <= section_level or not include_subsections:
                            break
                    section_lines.append(line)

            content = "".join(section_lines)
            return [TextContent(type="text", text=content)]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "markdown_update_section":
        file_path = Path(arguments["file_path"])
        heading = arguments["heading"]
        new_content = arguments["new_content"]
        include_subsections = arguments.get("include_subsections", True)

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Find and replace section
            new_lines = []
            in_section = False
            section_level = 0

            for line in lines:
                match = re.match(r"^(#{1,6})\s+(.+)$", line)

                if (
                    match
                    and match.group(2).strip() == heading.strip().lstrip("#").strip()
                ):
                    in_section = True
                    section_level = len(match.group(1))
                    # Add new content
                    new_lines.append(new_content)
                    if not new_content.endswith("\n"):
                        new_lines.append("\n")
                elif in_section:
                    if match:
                        current_level = len(match.group(1))
                        if current_level <= section_level or not include_subsections:
                            in_section = False
                            new_lines.append(line)
                else:
                    new_lines.append(line)

            # Atomic write
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            temp_path.rename(file_path)

            return [
                TextContent(type="text", text=json.dumps({"success": True}, indent=2))
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    elif name == "markdown_append":
        file_path = Path(arguments["file_path"])
        content = arguments["content"]

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)

            return [
                TextContent(type="text", text=json.dumps({"success": True}, indent=2))
            ]
        except Exception as e:
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult:
    """Handle a tool call, reporting failures as an is_error result.

    mcp 2.x turns handler exceptions into JSON-RPC errors, so unknown tools and
    unexpected failures are caught here and returned as ``is_error`` results.
    """
    try:
        content: list[ContentBlock] = list(
            await _dispatch(params.name, params.arguments or {})
        )
    except Exception as e:
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))
            ],
            is_error=True,
        )
    return CallToolResult(content=content)


# Register the handlers above on the server (mcp 2.x constructor kwargs).
mcp = Server("markdown-utils", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
