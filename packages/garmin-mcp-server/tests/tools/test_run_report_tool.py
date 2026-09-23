"""Unit tests for the ``get_run_report`` ToolDef registration and dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch, to_mcp_input_schema


@pytest.mark.unit
def test_get_run_report_tool_registered() -> None:
    """The tool is on the registry and takes a required integer activity_id."""
    tool = ALL_DEFS_BY_NAME["get_run_report"]
    schema = to_mcp_input_schema(tool.params, tool.field_descriptions)

    assert schema["type"] == "object"
    assert schema["properties"]["activity_id"]["type"] == "integer"
    assert schema["required"] == ["activity_id"]


@pytest.mark.unit
def test_get_run_report_tool_delegates_to_reader() -> None:
    """The handler forwards the id and returns the reader's payload unchanged."""
    reader = MagicMock()
    reader.get_run_report.return_value = {"activity_id": 123, "headline": {}}

    result = dispatch(ALL_DEFS_BY_NAME, reader, "get_run_report", {"activity_id": 123})

    reader.get_run_report.assert_called_once_with(123)
    assert result == {"activity_id": 123, "headline": {}}


@pytest.mark.unit
def test_get_run_note_inputs_returns_report_and_context() -> None:
    """One call carries the report and the coach subset of the bundle (#1362)."""
    reader = MagicMock()
    reader.get_run_report.return_value = {"activity_id": 123, "moments": []}
    bundle = {"training_type": "easy", "prescription": [{"prescription_id": 1}]}

    with patch(
        "garmin_mcp.scripts.prefetch_activity_context.prefetch_activity_context",
        return_value=bundle,
    ) as prefetch:
        result = dispatch(
            ALL_DEFS_BY_NAME, reader, "get_run_note_inputs", {"activity_id": 123}
        )

    prefetch.assert_called_once_with(123)
    assert isinstance(result, dict)
    assert result["activity_id"] == 123
    assert result["report"] == {"activity_id": 123, "moments": []}
    assert result["context"]["training_type"] == "easy"
    assert "prescription" not in result["context"]  # raw rows stay out


@pytest.mark.unit
def test_get_run_note_inputs_errors_when_report_missing() -> None:
    """No report -> an error payload, and the bundle is not even built."""
    reader = MagicMock()
    reader.get_run_report.return_value = None

    with patch(
        "garmin_mcp.scripts.prefetch_activity_context.prefetch_activity_context"
    ) as prefetch:
        result = dispatch(
            ALL_DEFS_BY_NAME, reader, "get_run_note_inputs", {"activity_id": 999}
        )

    prefetch.assert_not_called()
    assert result == {
        "error": "activity 999 has no run report",
        "activity_id": 999,
    }
