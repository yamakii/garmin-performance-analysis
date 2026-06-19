"""Contract tests ensuring tool names stay in sync across schemas and registry.

The per-domain handler classes were removed in #340; tool dispatch is now driven
solely by the single-source registry (``garmin_mcp.tools.ALL_DEFS_BY_NAME``), so
these contracts are expressed against the registry plus the two server-level
tools handled directly in ``server.py``.
"""

from __future__ import annotations

import pytest

from garmin_mcp.tool_schemas import TOOL_NAMES, get_tool_definitions
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME

# Tools handled directly in server.py, not registered in ALL_DEFS_BY_NAME.
SERVER_TOOLS = {"reload_server", "get_server_info"}


@pytest.mark.unit
class TestToolContract:
    """Verify the tool-name registry stays in sync with the schema surface."""

    def test_tool_names_match_registry(self) -> None:
        """TOOL_NAMES == registry tool names + server tools."""
        expected = set(ALL_DEFS_BY_NAME) | SERVER_TOOLS
        missing_from_registry = expected - TOOL_NAMES
        extra_in_registry = TOOL_NAMES - expected

        assert (
            not missing_from_registry
        ), f"Tools in registry but missing from TOOL_NAMES: {missing_from_registry}"
        assert (
            not extra_in_registry
        ), f"Tools in TOOL_NAMES but not registered: {extra_in_registry}"

    def test_no_duplicate_tool_names_in_registry(self) -> None:
        """Each tool name appears exactly once in ALL_DEFS."""
        seen: dict[str, int] = {}
        for tool_def in ALL_DEFS:
            seen[tool_def.name] = seen.get(tool_def.name, 0) + 1
        duplicates = [name for name, count in seen.items() if count > 1]

        assert not duplicates, f"Duplicate tool names in ALL_DEFS: {duplicates}"
        # ALL_DEFS_BY_NAME is a dict, so it dedupes; the lengths must match.
        assert len(ALL_DEFS) == len(ALL_DEFS_BY_NAME)

    def test_all_tools_have_schemas(self) -> None:
        """Every tool in TOOL_NAMES has a schema in get_tool_definitions()."""
        schema_names = {t.name for t in get_tool_definitions()}
        missing = TOOL_NAMES - schema_names
        extra = schema_names - TOOL_NAMES

        assert not missing, f"Tools in TOOL_NAMES without schema: {missing}"
        assert not extra, f"Tools with schema but not in TOOL_NAMES: {extra}"

    def test_tool_schemas_have_required_fields(self) -> None:
        """Every tool schema has name, description, and inputSchema."""
        tools = get_tool_definitions()
        for tool in tools:
            assert tool.name, "Tool missing name"
            assert tool.description, f"Tool '{tool.name}' missing description"
            assert tool.inputSchema, f"Tool '{tool.name}' missing inputSchema"
