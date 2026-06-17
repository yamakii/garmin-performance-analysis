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
        field_descriptions: Optional per-tool override of property descriptions,
            applied after deriving the schema from ``params``. This lets several
            tools share a single params model while each gives a property (e.g.
            ``statistics_only``) its own MCP description.
    """

    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[[GarminDBReader, Any], object]
    cli_group: str
    cli_name: str
    input_schema_override: dict[str, Any] | None = None
    field_descriptions: dict[str, str] | None = None


def to_mcp_input_schema(
    params: type[BaseModel],
    field_descriptions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert a Pydantic model to a hand-written-equivalent MCP inputSchema.

    Pydantic's ``model_json_schema()`` emits ``title`` fields, ``$defs``, and
    ``anyOf`` wrappers for Optional types. This function strips that noise so the
    result matches the minimal hand-authored schemas the MCP server previously
    served (byte-for-byte dict equality):

    - top-level ``type`` is always ``"object"``
    - each property keeps only the meaningful JSON-Schema keys: ``type``,
      ``description``, ``enum`` (``Literal``), ``items`` (``list[T]``),
      ``minItems`` / ``maxItems`` (``Annotated[list[T], Field(min_length=...,
      max_length=...)]``), and ``default``
    - ``default`` is omitted when the Pydantic default is ``None`` (Optional
      fields without an explicit non-None default), and kept for explicit
      non-None defaults (``False``, ``"parquet"``, ``10`` ...)
    - ``dict[str, Any]`` fields normalize to ``{"type": "object"}`` (Pydantic's
      ``additionalProperties`` is stripped)
    - ``required`` is preserved (omitted when empty, matching the hand schemas)

    Args:
        params: The Pydantic model to derive the schema from.
        field_descriptions: Optional mapping of property name -> description that
            overwrites the derived ``description`` for those properties.
    """
    raw = params.model_json_schema()
    raw_props: dict[str, Any] = raw.get("properties", {})

    properties: dict[str, Any] = {}
    for prop_name, prop_schema in raw_props.items():
        normalized = _normalize_property(prop_schema)
        if field_descriptions and prop_name in field_descriptions:
            normalized["description"] = field_descriptions[prop_name]
        properties[prop_name] = normalized

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    required = raw.get("required")
    if required:
        schema["required"] = list(required)
    return schema


def _normalize_property(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """Reduce a single Pydantic property schema to the minimal MCP shape.

    Keeps ``type``, ``description``, ``enum``, ``items``, ``minItems`` /
    ``maxItems`` and ``default`` (the last only when the default is non-None),
    digging into the non-null ``anyOf`` branch for ``Optional[...]`` fields.
    """
    normalized: dict[str, Any] = {}

    # Resolve the "shape" source: for Optional[...] the type/enum/items live in
    # the first non-null ``anyOf`` branch; otherwise they are on prop_schema.
    shape: dict[str, Any] = prop_schema
    if "type" not in prop_schema and "anyOf" in prop_schema:
        for branch in prop_schema["anyOf"]:
            if branch.get("type") and branch.get("type") != "null":
                shape = branch
                break

    prop_type = shape.get("type")
    if prop_type is not None:
        normalized["type"] = prop_type

    # Description always lives on the outer property schema (Field(description=)).
    if "description" in prop_schema:
        normalized["description"] = prop_schema["description"]

    # Literal[...] -> enum (inlined by Pydantic; also handled inside anyOf).
    if "enum" in shape:
        normalized["enum"] = list(shape["enum"])

    # list[T] -> items; Annotated[list[T], Field(min/max_length)] -> minItems/maxItems.
    if "items" in shape:
        item_schema = shape["items"]
        normalized["items"] = (
            {"type": item_schema["type"]}
            if isinstance(item_schema, dict) and "type" in item_schema
            else item_schema
        )
    if "minItems" in shape:
        normalized["minItems"] = shape["minItems"]
    if "maxItems" in shape:
        normalized["maxItems"] = shape["maxItems"]

    # default: keep explicit non-None defaults, drop Optional's None default.
    if "default" in prop_schema and prop_schema["default"] is not None:
        normalized["default"] = prop_schema["default"]

    return normalized


def build_mcp_tools(defs: list[ToolDef]) -> list[Tool]:
    """Build MCP ``Tool`` objects from tool definitions."""
    tools: list[Tool] = []
    for d in defs:
        input_schema = (
            d.input_schema_override
            if d.input_schema_override is not None
            else to_mcp_input_schema(d.params, d.field_descriptions)
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
