"""Tests for the metadata tools (dispatched via the single-source registry)."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool


@pytest.mark.unit
class TestToolRegistration:
    """Metadata tools are registered in the single-source registry."""

    @pytest.mark.parametrize(
        "name",
        ["get_activity_by_date", "get_date_by_activity_id", "ingest_activity"],
    )
    def test_metadata_tool_registered(self, name: str) -> None:
        assert name in ALL_DEFS_BY_NAME


@pytest.mark.unit
class TestGetActivityByDate:
    """Test _get_activity_by_date via handle()."""

    @pytest.mark.asyncio
    async def test_single_result(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                12345,
                "Morning Run",
                datetime(2025, 10, 15, 7, 30, 0),
                10.5,
                3600,
                "Shoes",
                "Nike Vaporfly",
                None,
            ),
        ]

        with patch("duckdb.connect", return_value=mock_conn):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["activity_id"] == 12345
        assert data["activity_name"] == "Morning Run"
        assert data["distance_km"] == 10.5
        assert data["duration_seconds"] == 3600
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_result_includes_gear(self, mock_db_reader: MagicMock) -> None:
        """The shoe worn is part of a single activity's metadata (#1207)."""
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                12345,
                "Morning Run",
                datetime(2025, 10, 15, 7, 30, 0),
                10.5,
                3600,
                "Shoes",
                "Nike Vaporfly",
                "v15",
            ),
        ]

        with patch("duckdb.connect", return_value=mock_conn):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["gear_type"] == "Shoes"
        assert data["gear_model"] == "Nike Vaporfly"
        assert data["gear_nickname"] == "v15"
        assert data["gear_label"] == "Nike Vaporfly (v15)"

    @pytest.mark.asyncio
    async def test_no_results(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-01-01"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "No activities found" in data["error"]
        assert data["activities"] == []

    @pytest.mark.asyncio
    async def test_multiple_results(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                11111,
                "Morning Run",
                datetime(2025, 10, 15, 7, 0, 0),
                5.0,
                1800,
                "Shoes",
                "Nike Vaporfly",
                "v15",
            ),
            (
                22222,
                "Evening Run",
                datetime(2025, 10, 15, 18, 0, 0),
                8.0,
                2700,
                "Shoes",
                "asics novablast 4",
                None,
            ),
        ]

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "Multiple activities" in data["error"]
        assert len(data["activities"]) == 2
        assert data["activities"][0]["activity_id"] == 11111
        assert data["activities"][1]["activity_id"] == 22222

    @pytest.mark.asyncio
    async def test_activity_by_date_multiple_runs_message(
        self, mock_db_reader: MagicMock
    ) -> None:
        """The tool takes no activity_id, so the error must not ask for one."""
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (11111, "Morning Run", datetime(2025, 10, 15, 7, 0), 5.0, 1800)
            + (None, None, None),
            (22222, "Evening Run", datetime(2025, 10, 15, 18, 0), 8.0, 2700)
            + (None, None, None),
        ]

        with patch("duckdb.connect", return_value=mock_conn):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        error = json.loads(result[0].text)["error"]
        assert "activity_id" not in error
        assert "activities" in error

    @pytest.mark.asyncio
    async def test_multiple_results_include_gear(
        self, mock_db_reader: MagicMock
    ) -> None:
        """Each candidate activity carries its own shoe (#1207)."""
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                11111,
                "Morning Run",
                datetime(2025, 10, 15, 7, 0, 0),
                5.0,
                1800,
                "Shoes",
                "Nike Vaporfly",
                "v15",
            ),
            (
                22222,
                "Evening Run",
                datetime(2025, 10, 15, 18, 0, 0),
                8.0,
                2700,
                "Shoes",
                "asics novablast 4",
                None,
            ),
        ]

        with patch("duckdb.connect", return_value=mock_conn):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["activities"][0]["gear_label"] == "Nike Vaporfly (v15)"
        assert data["activities"][1]["gear_model"] == "asics novablast 4"
        assert data["activities"][1]["gear_label"] == "asics novablast 4"

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/nonexistent/path.duckdb"

        with patch(
            "duckdb.connect",
            side_effect=Exception("Connection failed"),
        ):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "Connection failed" in data["error"]

    @pytest.mark.asyncio
    async def test_start_time_none_handled(self, mock_db_reader: MagicMock) -> None:
        """Verify None start_time is serialized correctly."""
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (99999, "Run", None, 5.0, 1500, None, None, None),
        ]

        with patch(
            "duckdb.connect",
            return_value=mock_conn,
        ):
            result = dispatch_tool(
                mock_db_reader, "get_activity_by_date", {"date": "2025-10-15"}
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

        result = dispatch_tool(
            mock_db_reader, "get_date_by_activity_id", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["date"] == "2025-10-15"
        mock_db_reader.get_activity_date.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_not_found(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_activity_date.return_value = None

        result = dispatch_tool(
            mock_db_reader, "get_date_by_activity_id", {"activity_id": 99999}
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 99999
        assert data["date"] is None


@pytest.mark.unit
class TestIngestActivity:
    """Test _ingest_activity via handle()."""

    @pytest.mark.asyncio
    async def test_ingest_activity_result_has_no_constant_fields(
        self, mock_db_reader: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_planner = MagicMock()
        mock_planner.execute_full_workflow.return_value = {
            "activity_id": 12345,
            "date": "2025-10-15",
            "form_evaluation_status": "success",
            "files": ["activity.json"],
            "timestamp": "2025-10-15T12:00:00",
        }

        with patch(
            "garmin_mcp.planner.workflow_planner.WorkflowPlanner",
            return_value=mock_planner,
        ):
            result = dispatch_tool(
                mock_db_reader, "ingest_activity", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data == {
            "success": True,
            "activity_id": 12345,
            "date": "2025-10-15",
            "form_evaluation_status": "success",
        }
        mock_planner.execute_full_workflow.assert_called_once_with(date="2025-10-15")

    def test_ingest_activity_params_reject_force_regenerate_absent(self) -> None:
        from garmin_mcp.tools.metadata import IngestActivityParams

        assert "force_regenerate" not in IngestActivityParams.model_fields

    @pytest.mark.asyncio
    async def test_workflow_error(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_planner = MagicMock()
        mock_planner.execute_full_workflow.side_effect = ValueError(
            "No activity found for 2025-01-01"
        )

        with patch(
            "garmin_mcp.planner.workflow_planner.WorkflowPlanner",
            return_value=mock_planner,
        ):
            result = dispatch_tool(
                mock_db_reader, "ingest_activity", {"date": "2025-01-01"}
            )

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "No activity found" in data["error"]

    @pytest.mark.asyncio
    async def test_date_stringified(self, mock_db_reader: MagicMock) -> None:
        """Verify datetime.date in result is stringified."""
        from datetime import date

        mock_db_reader.db_path = "/fake/path.duckdb"

        mock_planner = MagicMock()
        mock_planner.execute_full_workflow.return_value = {
            "activity_id": 12345,
            "date": date(2025, 10, 15),
            "form_evaluation_status": "success",
            "files": [],
            "timestamp": "2025-10-15T12:00:00",
        }

        with patch(
            "garmin_mcp.planner.workflow_planner.WorkflowPlanner",
            return_value=mock_planner,
        ):
            result = dispatch_tool(
                mock_db_reader, "ingest_activity", {"date": "2025-10-15"}
            )

        data = json.loads(result[0].text)
        assert data["date"] == "2025-10-15"
        assert isinstance(data["date"], str)


@pytest.mark.unit
class TestUnknownTool:
    """An unregistered tool name is not dispatchable via the registry.

    The MCP-facing ``ValueError`` contract lives in
    ``tests/handlers/test_server.py``.
    """

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(mock_db_reader, "nonexistent_tool", {})
