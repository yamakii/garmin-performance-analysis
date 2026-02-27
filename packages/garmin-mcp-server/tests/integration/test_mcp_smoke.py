"""MCP E2E smoke tests — handler-level integration tests."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.server import _dispatch_tool, _handle_get_server_info
from garmin_mcp.tool_schemas import get_tool_definitions


def _mock_get_connection(mock_conn):
    """Create a mock context manager for get_connection."""

    @contextmanager
    def _ctx(*args, **kwargs):
        yield mock_conn

    return _ctx


def _make_mock_conn(
    table_count: int = 14,
    last_date: str | None = "2025-10-15",
) -> MagicMock:
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        (f"t{i}",) for i in range(table_count)
    ]
    mock_conn.execute.return_value.fetchone.return_value = (last_date,)
    return mock_conn


@pytest.mark.integration
class TestMCPSmoke:
    """Smoke tests verifying MCP tool dispatch and health check."""

    def test_server_info_health(self) -> None:
        """get_server_info returns extended health fields."""
        mock_conn = _make_mock_conn(table_count=14, last_date="2025-10-15")
        with (
            patch(
                "garmin_mcp.server._get_server_dir",
                return_value="/mock/path",
            ),
            patch("garmin_mcp.server.os.path.exists", return_value=False),
            patch(
                "garmin_mcp.database.connection.get_connection",
                _mock_get_connection(mock_conn),
            ),
        ):
            result = _handle_get_server_info()

        data = json.loads(result[0].text)
        # Original fields
        assert "server_dir" in data
        assert "override_file_exists" in data
        # Extended fields
        assert data["db_status"] == "connected"
        assert data["table_count"] == 14
        assert data["last_ingest_date"] == "2025-10-15"
        assert isinstance(data["tool_count"], int)
        assert data["tool_count"] >= 30

    def test_tool_list_complete(self) -> None:
        """get_tool_definitions returns all registered tools."""
        tools = get_tool_definitions()
        assert len(tools) >= 30

        names = {t.name for t in tools}
        # Representative tools from each handler
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
        mock_conn = _make_mock_conn()
        with (
            patch(
                "garmin_mcp.server._get_server_dir",
                return_value="/mock/path",
            ),
            patch("garmin_mcp.server.os.path.exists", return_value=False),
            patch(
                "garmin_mcp.database.connection.get_connection",
                _mock_get_connection(mock_conn),
            ),
        ):
            result = await _dispatch_tool("get_server_info", {})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "server_dir" in data
        assert "db_status" in data
        assert "tool_count" in data

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_raises(self) -> None:
        """_dispatch_tool raises ValueError for unknown tool names."""
        with pytest.raises(ValueError, match="Unknown tool: nonexistent_tool"):
            await _dispatch_tool("nonexistent_tool", {})
