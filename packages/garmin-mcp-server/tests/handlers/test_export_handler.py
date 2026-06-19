"""Tests for the export tool (dispatched via the single-source registry)."""

import datetime
import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool


@pytest.mark.unit
class TestToolRegistration:
    """The export tool is registered in the single-source registry."""

    def test_export_registered(self) -> None:
        assert "export" in ALL_DEFS_BY_NAME


@pytest.mark.unit
class TestExportSuccess:
    """Test successful export via handle()."""

    @pytest.mark.asyncio
    async def test_export_with_defaults(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expires_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC).timestamp()
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.return_value = (
            "/tmp/export.parquet",
            "handle_abc123",
            expires_at,
        )
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )
        mock_db_reader.export_query_result.return_value = {
            "rows": 100,
            "size_mb": 0.5,
            "columns": ["a", "b"],
        }

        result = dispatch_tool(
            mock_db_reader, "export", {"query": "SELECT * FROM activities"}
        )

        data = json.loads(result[0].text)
        assert data["handle"] == "handle_abc123"
        assert data["rows"] == 100
        assert data["size_mb"] == 0.5
        assert data["columns"] == ["a", "b"]
        assert "expires_at" in data
        mock_export_mgr.create_export_handle.assert_called_once_with(
            export_format="parquet"
        )
        mock_db_reader.export_query_result.assert_called_once_with(
            query="SELECT * FROM activities",
            output_path="/tmp/export.parquet",
            export_format="parquet",
            max_rows=100000,
        )

    @pytest.mark.asyncio
    async def test_export_with_csv_format(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expires_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC).timestamp()
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.return_value = (
            "/tmp/export.csv",
            "handle_csv",
            expires_at,
        )
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )
        mock_db_reader.export_query_result.return_value = {
            "rows": 50,
            "size_mb": 0.1,
            "columns": ["x"],
        }

        result = dispatch_tool(
            mock_db_reader,
            "export",
            {"query": "SELECT x FROM t", "format": "csv", "max_rows": 500},
        )

        data = json.loads(result[0].text)
        assert data["handle"] == "handle_csv"
        assert data["rows"] == 50
        mock_export_mgr.create_export_handle.assert_called_once_with(
            export_format="csv"
        )
        mock_db_reader.export_query_result.assert_called_once_with(
            query="SELECT x FROM t",
            output_path="/tmp/export.csv",
            export_format="csv",
            max_rows=500,
        )

    @pytest.mark.asyncio
    async def test_export_returns_text_content(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expires_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC).timestamp()
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.return_value = (
            "/tmp/f.parquet",
            "h",
            expires_at,
        )
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )
        mock_db_reader.export_query_result.return_value = {
            "rows": 1,
            "size_mb": 0.0,
            "columns": [],
        }

        result = dispatch_tool(mock_db_reader, "export", {"query": "SELECT 1"})

        assert len(result) == 1
        assert result[0].type == "text"


@pytest.mark.unit
class TestExportValueError:
    """Test ValueError handling (e.g. size limit exceeded)."""

    @pytest.mark.asyncio
    async def test_value_error_returns_suggestion(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.side_effect = ValueError(
            "Result exceeds max rows"
        )
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )

        result = dispatch_tool(
            mock_db_reader, "export", {"query": "SELECT * FROM big_table"}
        )

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Result exceeds max rows" in data["error"]
        assert "suggestion" in data
        assert "Refine your query" in data["suggestion"]

    @pytest.mark.asyncio
    async def test_value_error_from_export_query(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expires_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC).timestamp()
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.return_value = (
            "/tmp/f.parquet",
            "h",
            expires_at,
        )
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )
        mock_db_reader.export_query_result.side_effect = ValueError("Invalid query")

        result = dispatch_tool(mock_db_reader, "export", {"query": "INVALID SQL"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Invalid query" in data["error"]
        assert "suggestion" in data


@pytest.mark.unit
class TestExportGeneralException:
    """Test general exception handling."""

    @pytest.mark.asyncio
    async def test_general_exception_returns_error(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_export_mgr = MagicMock()
        mock_export_mgr.create_export_handle.side_effect = RuntimeError("Disk full")
        mocker.patch(
            "garmin_mcp.mcp_server.export_manager.get_export_manager",
            return_value=mock_export_mgr,
        )

        result = dispatch_tool(mock_db_reader, "export", {"query": "SELECT 1"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Export failed: Disk full" in data["error"]
        assert "suggestion" not in data


@pytest.mark.unit
class TestUnknownTool:
    """An unregistered tool name is not dispatchable via the registry.

    ``server._dispatch_tool`` translates this into a ``ValueError`` for the MCP
    surface; that contract is covered in ``tests/handlers/test_server.py``.
    """

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(mock_db_reader, "nonexistent_tool", {"query": "SELECT 1"})
