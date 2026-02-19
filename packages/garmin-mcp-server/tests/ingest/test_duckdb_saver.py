"""Tests for garmin_mcp.ingest.duckdb_saver module."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from garmin_mcp.ingest.duckdb_saver import save_data, should_insert_table


@pytest.mark.unit
class TestShouldInsertTable:
    """Tests for should_insert_table helper."""

    def test_should_insert_table_none_tables(self) -> None:
        """When tables is None, all tables should be inserted."""
        assert should_insert_table("splits", None) is True

    def test_should_insert_table_in_list(self) -> None:
        """When table_name is in the tables list, return True."""
        assert should_insert_table("splits", ["splits", "activities"]) is True

    def test_should_insert_table_not_in_list(self) -> None:
        """When table_name is not in the tables list, return False."""
        assert should_insert_table("splits", ["activities"]) is False


@pytest.mark.unit
class TestSaveData:
    """Tests for save_data orchestration."""

    @staticmethod
    def _make_mock_conn() -> MagicMock:
        """Create a mock DuckDB connection."""
        return MagicMock()

    @staticmethod
    @contextmanager
    def _mock_write_context(conn: MagicMock):  # type: ignore[no-untyped-def]
        """Context manager that yields the mock connection."""
        yield conn

    def _patch_all_inserters(self, mocker: Any) -> dict[str, MagicMock]:
        """Patch all private inserter helper functions in duckdb_saver.

        Returns a dict of mock names to mock objects.
        """
        targets = {
            "activities": "garmin_mcp.ingest.duckdb_saver._insert_activities",
            "splits": "garmin_mcp.ingest.duckdb_saver._insert_table",
            "heart_rate_zones": "garmin_mcp.ingest.duckdb_saver._insert_heart_rate_zones",
            "hr_efficiency": "garmin_mcp.ingest.duckdb_saver._insert_hr_efficiency",
            "performance_trends": "garmin_mcp.ingest.duckdb_saver._insert_performance_trends",
            "lactate_threshold": "garmin_mcp.ingest.duckdb_saver._insert_lactate_threshold",
            "vo2_max": "garmin_mcp.ingest.duckdb_saver._insert_vo2_max",
            "time_series": "garmin_mcp.ingest.duckdb_saver._insert_time_series",
        }
        mocks = {}
        for name, target in targets.items():
            mocks[name] = mocker.patch(target)
        return mocks

    def test_save_data_happy_path(self, mocker: Any, tmp_path: Path) -> None:
        """Verify BEGIN TRANSACTION, inserter calls, and COMMIT on success."""
        mock_conn = self._make_mock_conn()
        mocker.patch(
            "garmin_mcp.database.connection.get_write_connection",
            return_value=self._mock_write_context(mock_conn),
        )
        inserter_mocks = self._patch_all_inserters(mocker)

        result = save_data(
            activity_id=12345,
            raw_data={},
            db_path="/tmp/test.duckdb",
            raw_dir=tmp_path,
            activity_date="2025-10-15",
            tables=None,
            base_weight_kg=70.0,
        )

        # Verify transaction lifecycle
        execute_calls = mock_conn.execute.call_args_list
        assert execute_calls[0] == call("BEGIN TRANSACTION")
        assert execute_calls[-1] == call("COMMIT")

        # Verify ROLLBACK was NOT called
        rollback_calls = [c for c in execute_calls if c == call("ROLLBACK")]
        assert len(rollback_calls) == 0

        # Verify inserters were called (activities and _insert_table for splits+form)
        inserter_mocks["activities"].assert_called_once()
        # _insert_table is called twice: once for splits, once for form_efficiency
        assert inserter_mocks["splits"].call_count == 2

        # Verify return value
        assert "raw_dir" in result

    def test_save_data_rollback_on_exception(self, mocker: Any, tmp_path: Path) -> None:
        """Verify ROLLBACK is called when an inserter raises, then re-raises."""
        mock_conn = self._make_mock_conn()
        mocker.patch(
            "garmin_mcp.database.connection.get_write_connection",
            return_value=self._mock_write_context(mock_conn),
        )
        inserter_mocks = self._patch_all_inserters(mocker)

        # Make activities inserter raise an exception
        inserter_mocks["activities"].side_effect = RuntimeError("DB insert failed")

        with pytest.raises(RuntimeError, match="DB insert failed"):
            save_data(
                activity_id=12345,
                raw_data={},
                db_path="/tmp/test.duckdb",
                raw_dir=tmp_path,
                activity_date="2025-10-15",
                tables=None,
            )

        # Verify ROLLBACK was called
        execute_calls = mock_conn.execute.call_args_list
        assert call("ROLLBACK") in execute_calls

        # Verify COMMIT was NOT called
        assert call("COMMIT") not in execute_calls

    def test_save_data_with_tables_filter(self, mocker: Any, tmp_path: Path) -> None:
        """When tables=["splits"], only splits inserter should be called."""
        mock_conn = self._make_mock_conn()
        mocker.patch(
            "garmin_mcp.database.connection.get_write_connection",
            return_value=self._mock_write_context(mock_conn),
        )
        inserter_mocks = self._patch_all_inserters(mocker)

        save_data(
            activity_id=12345,
            raw_data={},
            db_path="/tmp/test.duckdb",
            raw_dir=tmp_path,
            activity_date="2025-10-15",
            tables=["splits"],
        )

        # Verify COMMIT (no error)
        execute_calls = mock_conn.execute.call_args_list
        assert call("COMMIT") in execute_calls

        # _insert_table called once for splits (not for form_efficiency)
        assert inserter_mocks["splits"].call_count == 1
        # The call should be for "splits" table
        first_call_args = inserter_mocks["splits"].call_args
        assert first_call_args[0][0] == "splits"  # first positional arg is table_name

        # activities inserter should NOT be called (not in tables list)
        inserter_mocks["activities"].assert_not_called()

        # Other inserters should NOT be called
        inserter_mocks["heart_rate_zones"].assert_not_called()
        inserter_mocks["hr_efficiency"].assert_not_called()
        inserter_mocks["performance_trends"].assert_not_called()
        inserter_mocks["lactate_threshold"].assert_not_called()
        inserter_mocks["vo2_max"].assert_not_called()
        inserter_mocks["time_series"].assert_not_called()
