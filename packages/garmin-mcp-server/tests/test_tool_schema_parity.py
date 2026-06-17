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
        "properties": {"activity_id": {"type": "integer"}},
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
        "description": "User ID (default: 'default')",
        "default": "default",
    }
    assert props["condition_group"] == {
        "type": "string",
        "description": "Condition group (default: 'flat_road')",
        "default": "flat_road",
    }
    # No title/$defs/anyOf noise leaks through.
    assert "$defs" not in schema
    assert all("title" not in p for p in props.values())


@pytest.mark.unit
def test_schema_parity_physiology() -> None:
    built = build_mcp_tools(PHYSIOLOGY_TOOLS)
    built_by_name = {
        t.name: {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in built
    }

    # Reconstruct the original hand-written physiology schemas (pre-registry) to
    # assert byte-for-byte equality. These mirror tool_schemas._PHYSIOLOGY_TOOLS
    # before it was migrated to the registry.
    hand_schemas = {
        "get_form_efficiency_summary": {
            "name": "get_form_efficiency_summary",
            "description": (
                "Get form efficiency summary (GCT, VO, VR metrics) from "
                "form_efficiency table"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
        "get_form_evaluations": {
            "name": "get_form_evaluations",
            "description": (
                "Get pace-corrected form evaluation results (expected values, "
                "actual values, scores, star ratings, evaluation texts)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
        "get_form_baseline_trend": {
            "name": "get_form_baseline_trend",
            "description": (
                "Get form baseline trend (1-month coefficient comparison for "
                "form_trend analysis)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "activity_date": {
                        "type": "string",
                        "description": "Activity date in YYYY-MM-DD format",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID (default: 'default')",
                        "default": "default",
                    },
                    "condition_group": {
                        "type": "string",
                        "description": "Condition group (default: 'flat_road')",
                        "default": "flat_road",
                    },
                },
                "required": ["activity_id", "activity_date"],
            },
        },
        "get_hr_efficiency_analysis": {
            "name": "get_hr_efficiency_analysis",
            "description": (
                "Get HR efficiency analysis (zone distribution, training type) "
                "from hr_efficiency table"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
        "get_heart_rate_zones_detail": {
            "name": "get_heart_rate_zones_detail",
            "description": (
                "Get heart rate zones detail (boundaries, time distribution) "
                "from heart_rate_zones table"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
        "get_vo2_max_data": {
            "name": "get_vo2_max_data",
            "description": (
                "Get VO2 max data (precise value, fitness age, category) from "
                "vo2_max table"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
        "get_lactate_threshold_data": {
            "name": "get_lactate_threshold_data",
            "description": (
                "Get lactate threshold data (HR, speed, power) from "
                "lactate_threshold table"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"activity_id": {"type": "integer"}},
                "required": ["activity_id"],
            },
        },
    }

    assert set(built_by_name) == set(hand_schemas)
    for name, hand in hand_schemas.items():
        assert built_by_name[name] == hand, f"schema mismatch for {name}"

    # And the live MCP surface (get_tool_definitions) serves identical dicts.
    live = {
        t.name: {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in tool_schemas.get_tool_definitions()
        if t.name in hand_schemas
    }
    assert live == hand_schemas


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
