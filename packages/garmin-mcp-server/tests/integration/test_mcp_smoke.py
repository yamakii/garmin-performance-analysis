"""MCP shim smoke tests — handler-level integration with a mocked worker.

The shim delegates domain work to the worker; these smoke tests mock the worker
to verify the shim's wiring (info merge, dispatch routing, unknown-tool surfacing)
without spawning a subprocess.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

import garmin_mcp.server as server
from garmin_mcp.server import _dispatch_tool, _handle_get_server_info
from garmin_mcp.tool_schemas import get_tool_definitions


@pytest.mark.integration
class TestMCPSmoke:
    """Smoke tests verifying MCP tool dispatch and health check."""

    @pytest.mark.asyncio
    async def test_server_info_health(self) -> None:
        """get_server_info returns merged shim + worker health fields."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": True,
            "data": {
                "db_path": "/x/db.duckdb",
                "started_at": "2025-10-15T00:00:00+00:00",
                "table_count": 14,
                "last_ingest_date": "2025-10-15",
            },
        }
        with patch.object(server, "worker", worker):
            result = await _handle_get_server_info()

        data = json.loads(result[0].text)
        assert "started_at" in data
        assert data["ready"] is True
        assert data["db_status"] == "connected"
        assert data["table_count"] == 14
        assert data["last_ingest_date"] == "2025-10-15"

    def test_tool_list_complete(self) -> None:
        """get_tool_definitions returns all registered tools (registry source)."""
        tools = get_tool_definitions()
        assert len(tools) >= 30

        names = {t.name for t in tools}
        expected_subset = {
            "get_server_info",
            "reload_server",
            "get_activity_by_date",
            "get_splits_comprehensive",
            "get_form_evaluations",
            "get_hr_efficiency_analysis",
            "get_performance_trends",
            "export",
            "compare_similar_workouts",
        }
        missing = expected_subset - names
        assert not missing, f"Missing tools: {missing}"

    @pytest.mark.asyncio
    async def test_dispatch_get_server_info(self) -> None:
        """_dispatch_tool routes get_server_info correctly."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": True,
            "data": {"table_count": 1, "started_at": "t", "last_ingest_date": None},
        }
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("get_server_info", {})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "started_at" in data
        assert "db_status" in data
        assert "table_count" in data

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_surfaces_worker_error(self) -> None:
        """An unknown tool is surfaced as a worker error payload, not raised."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": False,
            "error": "Unknown tool: nonexistent_tool",
        }
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("nonexistent_tool", {})

        data = json.loads(result[0].text)
        assert "Unknown tool: nonexistent_tool" in data["error"]
