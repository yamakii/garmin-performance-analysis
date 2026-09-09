"""Unit tests for the worker IPC ``handle()`` dispatcher.

These exercise the in-process request handling (schema/call/info/unknown op)
with a mocked ``GarminDBReader``; the subprocess round-trip lives in the
integration suite.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS
from garmin_mcp.worker import handle


@pytest.mark.unit
def test_handle_schema_returns_tool_list() -> None:
    """``op=schema`` returns the full domain tool schema list."""
    reader = MagicMock()
    resp = handle({"id": 1, "op": "schema"}, reader)

    assert resp["ok"] is True
    assert resp["id"] == 1

    names = {tool["name"] for tool in resp["data"]}
    assert "get_performance_trends" in names
    assert len(resp["data"]) == len(ALL_DEFS)

    # Each entry carries the MCP boundary fields and stays JSON-serializable.
    sample = resp["data"][0]
    assert {"name", "description", "inputSchema"} <= set(sample)
    json.dumps(resp["data"])


@pytest.mark.unit
def test_handle_call_dispatches_to_registry() -> None:
    """``op=call`` routes through the registry dispatch to the reader."""
    reader = MagicMock()
    reader.get_activity_date.return_value = "2025-10-09"

    resp = handle(
        {
            "id": 7,
            "op": "call",
            "tool": "get_date_by_activity_id",
            "args": {"activity_id": 20636804823},
        },
        reader,
    )

    assert resp["ok"] is True
    assert resp["id"] == 7
    assert resp["data"] is not None
    assert resp["data"]["activity_id"] == 20636804823
    assert resp["data"]["date"] == "2025-10-09"
    reader.get_activity_date.assert_called_once_with(20636804823)


@pytest.mark.unit
def test_handle_call_invalid_args_returns_error() -> None:
    """Missing/invalid args surface as ``ok=False`` with a Pydantic message."""
    reader = MagicMock()

    resp = handle(
        {"id": 3, "op": "call", "tool": "get_date_by_activity_id", "args": {}},
        reader,
    )

    assert resp["ok"] is False
    assert resp["id"] == 3
    assert "error" in resp
    # Pydantic validation error mentions the missing field.
    assert "activity_id" in resp["error"]
    reader.get_date_by_activity_id.assert_not_called()


@pytest.mark.unit
def test_handle_unknown_op_returns_error() -> None:
    """An unrecognized ``op`` returns ``ok=False`` without raising."""
    reader = MagicMock()
    resp = handle({"id": 9, "op": "bogus"}, reader)

    assert resp["ok"] is False
    assert resp["id"] == 9
    assert "bogus" in resp["error"]


@pytest.mark.unit
def test_handle_info_returns_db_diagnostics() -> None:
    """``op=info`` returns DB diagnostics with an int table_count and started_at."""
    reader = MagicMock()
    resp = handle({"id": 5, "op": "info"}, reader)

    assert resp["ok"] is True
    assert resp["id"] == 5
    data = resp["data"]
    assert isinstance(data["table_count"], int)
    assert "started_at" in data
    # Whole response must be JSON-serializable (MCP boundary).
    json.dumps(resp)
