"""Core registry types and helpers for single-source tool definitions.

A ``ToolDef`` declares everything needed to expose a tool across surfaces:

- the MCP ``inputSchema`` (derived from a Pydantic ``params`` model, or an
  explicit ``input_schema_override`` escape hatch for special tools)
- dispatch (``handler`` receives the reader + a validated params instance)
- CLI grouping (``cli_group`` / ``cli_name``)

``to_mcp_input_schema`` normalizes Pydantic's ``model_json_schema()`` output so
that the produced schema is byte-identical to the hand-written schemas that the
MCP server previously served (no ``title``/``$defs``/``anyOf`` noise).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.types import Tool
from pydantic import BaseModel

if TYPE_CHECKING:
    from garmin_mcp.database.db_reader import GarminDBReader


@dataclass(frozen=True)
class ToolDef:
    """Single-source declaration of a tool.

    Attributes:
        name: MCP tool name (also used for dispatch lookup).
        description: MCP tool description (verbatim, byte-parity with hand schema).
        params: Pydantic model describing the tool arguments.
        handler: Callable invoked with ``(reader, params_instance)`` -> result.
        cli_group: Typer sub-app name (e.g. ``"physiology"``).
        cli_name: Typer command name within the group (e.g. ``"hr-efficiency"``).
        input_schema_override: Explicit MCP ``inputSchema`` for special tools that
            cannot be expressed via the standard normalization. When set, it is
            used verbatim instead of deriving from ``params``.
    """

    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[[GarminDBReader, Any], object]
    cli_group: str
    cli_name: str
    input_schema_override: dict[str, Any] | None = None


def to_mcp_input_schema(params: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model to a hand-written-equivalent MCP inputSchema.

    Pydantic's ``model_json_schema()`` emits ``title`` fields, ``$defs``, and
    ``anyOf`` wrappers for Optional types. This function strips that noise so the
    result matches the minimal hand-authored schemas the MCP server previously
    served (byte-for-byte dict equality):

    - top-level ``type`` is always ``"object"``
    - each property keeps only ``type`` plus optional ``description`` / ``default``
    - ``required`` is preserved (omitted when empty, matching the hand schemas)
    """
    raw = params.model_json_schema()
    raw_props: dict[str, Any] = raw.get("properties", {})

    properties: dict[str, Any] = {}
    for prop_name, prop_schema in raw_props.items():
        properties[prop_name] = _normalize_property(prop_schema)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    required = raw.get("required")
    if required:
        schema["required"] = list(required)
    return schema


def _normalize_property(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """Reduce a single Pydantic property schema to ``type``/``description``/``default``."""
    normalized: dict[str, Any] = {}

    prop_type = prop_schema.get("type")
    if prop_type is None and "anyOf" in prop_schema:
        # Optional[...] surfaces as anyOf [{type: X}, {type: null}]; take the
        # first non-null branch's type.
        for branch in prop_schema["anyOf"]:
            if branch.get("type") and branch.get("type") != "null":
                prop_type = branch["type"]
                break
    if prop_type is not None:
        normalized["type"] = prop_type

    if "description" in prop_schema:
        normalized["description"] = prop_schema["description"]
    if "default" in prop_schema:
        normalized["default"] = prop_schema["default"]

    return normalized


def build_mcp_tools(defs: list[ToolDef]) -> list[Tool]:
    """Build MCP ``Tool`` objects from tool definitions."""
    tools: list[Tool] = []
    for d in defs:
        input_schema = (
            d.input_schema_override
            if d.input_schema_override is not None
            else to_mcp_input_schema(d.params)
        )
        tools.append(
            Tool(
                name=d.name,
                description=d.description,
                inputSchema=input_schema,
            )
        )
    return tools


def dispatch(
    defs_by_name: dict[str, ToolDef],
    reader: GarminDBReader,
    name: str,
    arguments: dict[str, Any],
) -> object:
    """Validate arguments and dispatch to the tool's handler.

    Args:
        defs_by_name: Lookup of tool name -> ToolDef.
        reader: GarminDBReader instance passed to the handler.
        name: Tool name to dispatch.
        arguments: Raw argument dict (validated against the ToolDef's params).

    Returns:
        The handler's return value.

    Raises:
        KeyError: If ``name`` is not a registered tool.
    """
    tool_def = defs_by_name[name]
    params_instance = tool_def.params(**arguments)
    return tool_def.handler(reader, params_instance)
