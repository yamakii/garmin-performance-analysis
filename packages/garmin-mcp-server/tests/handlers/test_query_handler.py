"""query_db / get_db_catalog dispatch through the single-source registry (#1604)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool


@pytest.mark.unit
class TestQueryTools:
    def test_query_db_and_catalog_registered(self) -> None:
        assert "query_db" in ALL_DEFS_BY_NAME
        assert "get_db_catalog" in ALL_DEFS_BY_NAME

    def test_query_db_max_rows_bounds(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(Exception, match="max_rows"):
            dispatch_tool(
                mock_db_reader, "query_db", {"sql": "SELECT 1", "max_rows": 201}
            )
        mock_db_reader.run_inline_query.assert_not_called()

    def test_query_db_dispatches_to_reader(self, mock_db_reader: MagicMock) -> None:
        payload = {
            "columns": ["a"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "note": None,
        }
        mock_db_reader.run_inline_query.return_value = payload
        result = dispatch_tool(
            mock_db_reader, "query_db", {"sql": "SELECT 1 AS a", "max_rows": 10}
        )
        mock_db_reader.run_inline_query.assert_called_once_with("SELECT 1 AS a", 10)
        assert json.loads(result[0].text) == payload

    def test_get_db_catalog_dispatches_table(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.db_catalog.return_value = {"tables": []}
        dispatch_tool(mock_db_reader, "get_db_catalog", {})
        mock_db_reader.db_catalog.assert_called_once_with(None)
        mock_db_reader.db_catalog.reset_mock()
        dispatch_tool(mock_db_reader, "get_db_catalog", {"table": "splits"})
        mock_db_reader.db_catalog.assert_called_once_with("splits")
