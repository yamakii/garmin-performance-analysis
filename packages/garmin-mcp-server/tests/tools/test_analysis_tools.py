"""Unit tests for the analysis-domain ToolDef surface."""

from __future__ import annotations

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import to_mcp_input_schema


@pytest.mark.unit
def test_analysis_tools_enum_is_run_note() -> None:
    """The MCP surface offers exactly one section type (Issue #1256)."""
    for name in ("get_analysis_contract", "validate_section_json"):
        tool = ALL_DEFS_BY_NAME[name]
        schema = to_mcp_input_schema(tool.params, tool.field_descriptions)

        assert schema["properties"]["section_type"]["enum"] == ["run_note"]
