"""Tests for ExportHandler."""

import datetime
import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.export_handler import ExportHandler


class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_export(self, mock_db_reader: MagicMock) -> None:
        handler = ExportHandler(mock_db_reader)
        assert handler.handles("export") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = ExportHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = ExportHandler(mock_db_reader)
        assert handler.handles("") is False


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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle("export", {"query": "SELECT * FROM activities"})

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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle("export", {"query": "SELECT 1"})

        assert len(result) == 1
        assert result[0].type == "text"


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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle("export", {"query": "SELECT * FROM big_table"})

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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle("export", {"query": "INVALID SQL"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Invalid query" in data["error"]
        assert "suggestion" in data


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
        handler = ExportHandler(mock_db_reader)

        result = await handler.handle("export", {"query": "SELECT 1"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Export failed: Disk full" in data["error"]
        assert "suggestion" not in data


class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = ExportHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"query": "SELECT 1"})
