"""Generate ``docs/mcp-tools-reference.md`` from the ToolDef registry.

The MCP tool surface is declared once in ``garmin_mcp.tools.ALL_DEFS`` (44 domain
tools) plus the 2 server tools in ``tool_schemas._SERVER_TOOLS``. This script
renders that registry into a single human-readable reference so the doc never
drifts from the code.

Usage::

    # Write/refresh the reference
    uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.generate_tool_reference

    # Verify the committed doc is in sync (used by the sync test / CI)
    uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.generate_tool_reference --check

A unit test (``tests/scripts/test_generate_tool_reference.py``) asserts the
committed doc equals ``render_reference()``, so adding a tool without
regenerating fails CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from garmin_mcp.tool_schemas import _SERVER_TOOLS
from garmin_mcp.tools import ALL_DEFS
from garmin_mcp.tools.registry import ToolDef, to_mcp_input_schema

# scripts -> garmin_mcp -> src -> garmin-mcp-server -> packages -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
DOC_PATH = REPO_ROOT / "docs" / "mcp-tools-reference.md"

# Human-readable section titles, keyed by ToolDef.cli_group, in display order.
GROUP_TITLES: dict[str, str] = {
    "export": "Export",
    "metadata": "Metadata",
    "splits": "Splits",
    "analysis": "Analysis",
    "physiology": "Physiology",
    "performance": "Performance",
    "time-series": "Time Series",
    "training-plan": "Training Plan",
    "athlete": "Athlete",
    "race": "Race",
    "load": "Training Load",
    "durability": "Durability",
}


def _tool_input_schema(d: ToolDef) -> dict[str, Any]:
    """Return the MCP inputSchema for a ToolDef (override or derived)."""
    if d.input_schema_override is not None:
        return d.input_schema_override
    return to_mcp_input_schema(d.params, d.field_descriptions)


def _param_type(prop: dict[str, Any]) -> str:
    """Render a JSON-schema property's type as a short string."""
    if "enum" in prop:
        values = ", ".join(f"`{v}`" for v in prop["enum"])
        return f"enum: {values}"
    prop_type = str(prop.get("type", "object"))
    if prop_type == "array":
        item_type = prop.get("items", {}).get("type", "any")
        return f"array[{item_type}]"
    return prop_type


def _param_requirement(name: str, prop: dict[str, Any], required: set[str]) -> str:
    """Render the required/optional/default cell for a property."""
    if name in required:
        return "**required**"
    if "default" in prop:
        return f"optional (default `{prop['default']}`)"
    return "optional"


def _render_params(schema: dict[str, Any]) -> list[str]:
    """Render a parameter table for one tool's inputSchema."""
    properties: dict[str, Any] = schema.get("properties", {})
    if not properties:
        return ["_No parameters._", ""]
    required = set(schema.get("required", []))
    lines = [
        "| Parameter | Type | Required | Description |",
        "|-----------|------|----------|-------------|",
    ]
    for name, prop in properties.items():
        desc = prop.get("description", "").replace("\n", " ").strip()
        lines.append(
            f"| `{name}` | {_param_type(prop)} "
            f"| {_param_requirement(name, prop, required)} | {desc} |"
        )
    lines.append("")
    return lines


def _render_tool(
    name: str, description: str, schema: dict[str, Any], cli: str | None
) -> list[str]:
    """Render one tool entry (heading + CLI + description + params)."""
    lines = [f"### `{name}`", ""]
    if cli is not None:
        lines += [f"CLI: `{cli}`", ""]
    lines += [description.replace("\n", " ").strip(), ""]
    lines += _render_params(schema)
    return lines


def render_reference() -> str:
    """Render the full MCP tools reference markdown from the registry."""
    total = len(ALL_DEFS) + len(_SERVER_TOOLS)

    # Group domain tools by cli_group, preserving ALL_DEFS first-appearance order.
    groups: dict[str, list[ToolDef]] = {}
    for d in ALL_DEFS:
        groups.setdefault(d.cli_group, []).append(d)

    lines: list[str] = [
        "# MCP Tools Reference",
        "",
        f"Auto-generated from the `ToolDef` registry "
        f"(`garmin_mcp.tools.ALL_DEFS`) — **{total} tools** "
        f"({len(ALL_DEFS)} domain + {len(_SERVER_TOOLS)} server). "
        "Do not edit by hand.",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "uv run --directory packages/garmin-mcp-server \\",
        "  python -m garmin_mcp.scripts.generate_tool_reference",
        "```",
        "",
        "Tools are callable as MCP tools (`mcp__garmin-db__<name>`) and, for "
        "domain tools, via the reloadless `garmin-db` CLI. Return shapes are not "
        "captured by the registry — call a tool (or read its handler) for the "
        "response structure.",
        "",
        "## Contents",
        "",
    ]
    for group in groups:
        title = GROUP_TITLES.get(group, group)
        anchor = title.lower().replace(" ", "-")
        lines.append(f"- [{title}](#{anchor}) ({len(groups[group])})")
    lines.append(f"- [Server](#server) ({len(_SERVER_TOOLS)})")
    lines.append("")

    for group, defs in groups.items():
        title = GROUP_TITLES.get(group, group)
        lines += [f"## {title}", ""]
        for d in defs:
            cli = f"garmin-db {d.cli_group} {d.cli_name}"
            lines += _render_tool(d.name, d.description, _tool_input_schema(d), cli)

    # Server tools (handled in server.py, not part of the registry).
    lines += ["## Server", ""]
    for tool in _SERVER_TOOLS:
        lines += _render_tool(
            tool["name"], tool["description"], tool["inputSchema"], cli=None
        )

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed doc differs from the generated output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DOC_PATH,
        help=f"Output path (default: {DOC_PATH})",
    )
    args = parser.parse_args(argv)

    content = render_reference()

    if args.check:
        if not args.output.exists():
            print(f"MISSING: {args.output} does not exist. Run without --check.")
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != content:
            print(
                f"OUT OF SYNC: {args.output} differs from the registry. "
                "Regenerate with: python -m garmin_mcp.scripts.generate_tool_reference"
            )
            return 1
        print(
            f"OK: {args.output} is in sync ({len(ALL_DEFS) + len(_SERVER_TOOLS)} tools)."
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output} ({len(ALL_DEFS) + len(_SERVER_TOOLS)} tools).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
