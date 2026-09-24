"""Unit tests for the single-source tool registry (schema + dispatch).

Guards the byte-for-byte parity contract: the registry-derived physiology
schemas must equal the previously hand-written MCP schemas, and dispatch must
route to the correct reader method.
"""

from unittest.mock import MagicMock

import pytest

import garmin_mcp.tool_schemas as tool_schemas
from garmin_mcp.tools.physiology import (
    PHYSIOLOGY_TOOLS,
    PHYSIOLOGY_TOOLS_BY_NAME,
    ActivityIdParams,
    FormBaselineTrendParams,
)
from garmin_mcp.tools.registry import (
    build_mcp_tools,
    dispatch,
    to_mcp_input_schema,
)


@pytest.mark.unit
def test_to_mcp_input_schema_activity_id() -> None:
    schema = to_mcp_input_schema(ActivityIdParams)
    assert schema == {
        "type": "object",
        "properties": {
            "activity_id": {
                "type": "integer",
                "description": (
                    "Garmin activity ID (resolve one from a date with "
                    "get_activity_by_date)"
                ),
            }
        },
        "required": ["activity_id"],
    }


@pytest.mark.unit
def test_to_mcp_input_schema_optional_defaults() -> None:
    schema = to_mcp_input_schema(FormBaselineTrendParams)

    # Required: only fields without defaults.
    assert schema["required"] == ["activity_id", "activity_date"]
    assert "user_id" not in schema["required"]
    assert "condition_group" not in schema["required"]

    props = schema["properties"]
    # Optional fields surface their default value in the schema.
    assert props["user_id"] == {
        "type": "string",
        "description": "Baseline owner (default: 'default')",
        "default": "default",
    }
    assert props["condition_group"] == {
        "type": "string",
        "description": (
            "Baseline condition group (default: 'flat_road', the group the "
            "baseline scripts train)"
        ),
        "default": "flat_road",
    }
    # No title/$defs/anyOf noise leaks through.
    assert "$defs" not in schema
    assert all("title" not in p for p in props.values())


@pytest.mark.unit
def test_schema_parity_physiology() -> None:
    """The registry-built physiology schemas are what the live MCP surface serves.

    The wording itself is pinned by the golden snapshot
    (``test_all_tools_registry.test_schema_parity_all_tools``).
    """
    built = {
        t.name: (t.description, t.input_schema)
        for t in build_mcp_tools(PHYSIOLOGY_TOOLS)
    }
    live = {
        t.name: (t.description, t.input_schema)
        for t in tool_schemas.get_tool_definitions()
        if t.name in built
    }
    assert set(built) == set(PHYSIOLOGY_TOOLS_BY_NAME)
    assert live == built


@pytest.mark.unit
def test_dispatch_routes_to_reader() -> None:
    reader = MagicMock()
    reader.get_hr_efficiency_analysis.return_value = {"activity_id": 123}

    result = dispatch(
        PHYSIOLOGY_TOOLS_BY_NAME,
        reader,
        "get_hr_efficiency_analysis",
        {"activity_id": 123},
    )

    reader.get_hr_efficiency_analysis.assert_called_once_with(123)
    assert result == {"activity_id": 123}


@pytest.mark.unit
def test_dispatch_unknown_tool_raises() -> None:
    reader = MagicMock()
    with pytest.raises(KeyError):
        dispatch(PHYSIOLOGY_TOOLS_BY_NAME, reader, "no_such_tool", {})


@pytest.mark.unit
def test_server_tool_schemas_match_server_descriptions() -> None:
    """The reference docs' server tools carry the shim's own descriptions."""
    from garmin_mcp import server
    from garmin_mcp.server_tools import SERVER_TOOLS

    assert server._SERVER_TOOLS is SERVER_TOOLS
    assert [
        {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
        for t in SERVER_TOOLS
    ] == tool_schemas._SERVER_TOOLS
    served = {t.name: t.description for t in tool_schemas.get_tool_definitions()}
    for t in SERVER_TOOLS:
        assert served[t.name] == t.description
