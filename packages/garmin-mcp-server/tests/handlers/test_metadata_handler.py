"""Tests for MetadataHandler."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.handlers.metadata_handler import MetadataHandler


@pytest.mark.unit
class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_activity_by_date(self, mock_db_reader: MagicMock) -> None:
        handler = MetadataHandler(mock_db_reader)
        assert handler.handles("get_activity_by_date") is True

    def test_handles_get_date_by_activity_id(self, mock_db_reader: MagicMock) -> None:
        handler = MetadataHandler(mock_db_reader)
        assert handler.handles("get_date_by_activity_id") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = MetadataHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = MetadataHandler(mock_db_reader)
        assert handler.handles("") is False


@pytest.mark.unit
class TestGetActivityByDate:
    """Test _get_activity_by_date via handle()."""

    @pytest.mark.asyncio
    async def test_single_result(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"
        handler = MetadataHandler(mock_db_reader)

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (12345, "Morning Run", datetime(2025, 10, 15, 7, 30, 0), 10.5, 3600),
        ]

        with patch("duckdb.connect", return_value=mock_conn):
            result = await handler.handle(
                "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["activity_id"] == 12345
        assert data["activity_name"] == "Morning Run"
        assert data["distance_km"] == 10.5
        assert data["duration_seconds"] == 3600
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_results(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"
        handler = MetadataHandler(mock_db_reader)

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = await handler.handle(
                "get_activity_by_date", {"date": "2025-01-01"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "No activities found" in data["error"]
        assert data["activities"] == []

    @pytest.mark.asyncio
    async def test_multiple_results(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"
        handler = MetadataHandler(mock_db_reader)

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (11111, "Morning Run", datetime(2025, 10, 15, 7, 0, 0), 5.0, 1800),
            (22222, "Evening Run", datetime(2025, 10, 15, 18, 0, 0), 8.0, 2700),
        ]

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = await handler.handle(
                "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "Multiple activities" in data["error"]
        assert len(data["activities"]) == 2
        assert data["activities"][0]["activity_id"] == 11111
        assert data["activities"][1]["activity_id"] == 22222

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/nonexistent/path.duckdb"
        handler = MetadataHandler(mock_db_reader)

        with patch(
            "duckdb.connect",
            side_effect=Exception("Connection failed"),
        ):
            result = await handler.handle(
                "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "Connection failed" in data["error"]

    @pytest.mark.asyncio
    async def test_start_time_none_handled(self, mock_db_reader: MagicMock) -> None:
        """Verify None start_time is serialized correctly."""
        mock_db_reader.db_path = "/fake/path.duckdb"
        handler = MetadataHandler(mock_db_reader)

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (99999, "Run", None, 5.0, 1500),
        ]

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = await handler.handle(
                "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["start_time"] is None


@pytest.mark.unit
class TestGetDateByActivityId:
    """Test _get_date_by_activity_id via handle()."""

    @pytest.mark.asyncio
    async def test_found(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_activity_date.return_value = "2025-10-15"
        handler = MetadataHandler(mock_db_reader)

        result = await handler.handle("get_date_by_activity_id", {"activity_id": 12345})

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["date"] == "2025-10-15"
        mock_db_reader.get_activity_date.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_not_found(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_activity_date.return_value = None
        handler = MetadataHandler(mock_db_reader)

        result = await handler.handle("get_date_by_activity_id", {"activity_id": 99999})

        data = json.loads(result[0].text)
        assert data["activity_id"] == 99999
        assert data["date"] is None


@pytest.mark.unit
class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = MetadataHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {})
