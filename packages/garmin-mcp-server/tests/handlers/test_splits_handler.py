"""Tests for the splits tools (dispatched via the single-source registry)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool

ACTIVITY_ID = 20594901208


# -- registry membership tests ------------------------------------------------


@pytest.mark.unit
class TestToolRegistration:
    """Splits tools are registered in the single-source registry."""

    @pytest.mark.parametrize(
        "tool_name",
        ["get_splits_elevation", "get_splits_comprehensive"],
    )
    def test_splits_tool_registered(self, tool_name: str) -> None:
        assert tool_name in ALL_DEFS_BY_NAME

    @pytest.mark.parametrize(
        "tool_name",
        ["unknown_tool", "", "get_splits_pace_hr", "get_splits_form_metrics"],
    )
    def test_unknown_tool_not_registered(self, tool_name: str) -> None:
        # The per-family split tools are superseded by get_splits_comprehensive.
        assert tool_name not in ALL_DEFS_BY_NAME


# -- get_splits_elevation tests -----------------------------------------------


@pytest.mark.unit
class TestGetSplitsElevation:
    """Test get_splits_elevation handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_elevation.return_value = sample_splits_result

        result = dispatch_tool(
            mock_db_reader,
            "get_splits_elevation",
            {"activity_id": ACTIVITY_ID, "statistics_only": False},
        )

        mock_db_reader.get_splits_elevation.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )
        parsed = json.loads(result[0].text)
        assert parsed == sample_splits_result

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_true(
        self,
        mock_db_reader: MagicMock,
        sample_statistics_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_elevation.return_value = sample_statistics_result

        result = dispatch_tool(
            mock_db_reader,
            "get_splits_elevation",
            {"activity_id": ACTIVITY_ID, "statistics_only": True},
        )

        mock_db_reader.get_splits_elevation.assert_called_once_with(
            ACTIVITY_ID, statistics_only=True
        )
        parsed = json.loads(result[0].text)
        assert parsed["statistics_only"] is True

    @pytest.mark.asyncio
    async def test_returns_none_as_json_null(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_elevation.return_value = None

        result = dispatch_tool(
            mock_db_reader, "get_splits_elevation", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed is None


# -- get_splits_comprehensive tests -------------------------------------------


@pytest.mark.unit
class TestGetSplitsComprehensive:
    """Test get_splits_comprehensive handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_comprehensive.return_value = sample_splits_result

        result = dispatch_tool(
            mock_db_reader,
            "get_splits_comprehensive",
            {"activity_id": ACTIVITY_ID, "statistics_only": False},
        )

        mock_db_reader.get_splits_comprehensive.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )
        parsed = json.loads(result[0].text)
        assert parsed == sample_splits_result

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_true(
        self,
        mock_db_reader: MagicMock,
        sample_statistics_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_comprehensive.return_value = sample_statistics_result

        result = dispatch_tool(
            mock_db_reader,
            "get_splits_comprehensive",
            {"activity_id": ACTIVITY_ID, "statistics_only": True},
        )

        mock_db_reader.get_splits_comprehensive.assert_called_once_with(
            ACTIVITY_ID, statistics_only=True
        )
        parsed = json.loads(result[0].text)
        assert parsed["statistics_only"] is True

    @pytest.mark.asyncio
    async def test_defaults_statistics_only_to_false(
        self, mock_db_reader: MagicMock
    ) -> None:
        mock_db_reader.get_splits_comprehensive.return_value = {}

        dispatch_tool(
            mock_db_reader, "get_splits_comprehensive", {"activity_id": ACTIVITY_ID}
        )

        mock_db_reader.get_splits_comprehensive.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )


# -- Error handling tests -----------------------------------------------------


@pytest.mark.unit
class TestErrorHandling:
    """Test error cases."""

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(
                mock_db_reader, "nonexistent_tool", {"activity_id": ACTIVITY_ID}
            )
