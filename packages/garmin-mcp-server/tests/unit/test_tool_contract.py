"""Contract tests ensuring tool names stay in sync across schemas and handlers."""

from __future__ import annotations

from typing import Protocol

import pytest

from garmin_mcp.handlers.analysis_handler import AnalysisHandler
from garmin_mcp.handlers.export_handler import ExportHandler
from garmin_mcp.handlers.metadata_handler import MetadataHandler
from garmin_mcp.handlers.performance_handler import PerformanceHandler
from garmin_mcp.handlers.physiology_handler import PhysiologyHandler
from garmin_mcp.handlers.splits_handler import SplitsHandler
from garmin_mcp.handlers.time_series_handler import TimeSeriesHandler
from garmin_mcp.handlers.training_plan_handler import TrainingPlanHandler
from garmin_mcp.tool_schemas import TOOL_NAMES, get_tool_definitions


class _HasToolNames(Protocol):
    _tool_names: set[str]


HANDLER_CLASSES: list[type[_HasToolNames]] = [
    AnalysisHandler,
    ExportHandler,
    MetadataHandler,
    PerformanceHandler,
    PhysiologyHandler,
    SplitsHandler,
    TimeSeriesHandler,
    TrainingPlanHandler,
]

# Tools handled directly in server.py, not by any handler class
SERVER_TOOLS = {"reload_server", "get_server_info"}


@pytest.mark.unit
class TestToolContract:
    """Verify tool name registry stays in sync with handler definitions."""

    def test_tool_names_match_handlers(self) -> None:
        """TOOL_NAMES == union of all handler._tool_names + server tools."""
        handler_tools: set[str] = set()
        for handler_cls in HANDLER_CLASSES:
            handler_tools |= handler_cls._tool_names

        expected = handler_tools | SERVER_TOOLS
        missing_from_registry = expected - TOOL_NAMES
        extra_in_registry = TOOL_NAMES - expected

        assert (
            not missing_from_registry
        ), f"Tools in handlers but missing from TOOL_NAMES: {missing_from_registry}"
        assert (
            not extra_in_registry
        ), f"Tools in TOOL_NAMES but not in any handler: {extra_in_registry}"

    def test_no_duplicate_tool_names_across_handlers(self) -> None:
        """Each tool name appears in exactly one handler."""
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for handler_cls in HANDLER_CLASSES:
            for name in handler_cls._tool_names:
                if name in seen:
                    duplicates.append(
                        f"'{name}' in both {seen[name]} and {handler_cls.__name__}"
                    )
                seen[name] = handler_cls.__name__

        assert not duplicates, f"Duplicate tool names: {duplicates}"

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
