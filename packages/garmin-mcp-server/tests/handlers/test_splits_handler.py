"""Tests for SplitsHandler."""

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.config import DEFAULT_MAX_OUTPUT_SIZE
from garmin_mcp.handlers.splits_handler import SplitsHandler

ACTIVITY_ID = 20594901208


# -- handles() tests ----------------------------------------------------------


class TestHandles:
    """Test SplitsHandler.handles() routing."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_splits_pace_hr",
            "get_splits_form_metrics",
            "get_splits_elevation",
            "get_splits_comprehensive",
            "get_splits_all",
        ],
    )
    def test_handles_returns_true_for_known_tools(
        self, mock_db_reader: MagicMock, tool_name: str
    ) -> None:
        handler = SplitsHandler(mock_db_reader)
        assert handler.handles(tool_name) is True

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_activity_by_date",
            "unknown_tool",
            "",
            "get_splits_pace_hr_v2",
        ],
    )
    def test_handles_returns_false_for_unknown_tools(
        self, mock_db_reader: MagicMock, tool_name: str
    ) -> None:
        handler = SplitsHandler(mock_db_reader)
        assert handler.handles(tool_name) is False


# -- get_splits_pace_hr tests -------------------------------------------------


class TestGetSplitsPaceHr:
    """Test get_splits_pace_hr handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_pace_hr.return_value = sample_splits_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_pace_hr",
            {"activity_id": ACTIVITY_ID, "statistics_only": False},
        )

        mock_db_reader.get_splits_pace_hr.assert_called_once_with(
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
        mock_db_reader.get_splits_pace_hr.return_value = sample_statistics_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_pace_hr",
            {"activity_id": ACTIVITY_ID, "statistics_only": True},
        )

        mock_db_reader.get_splits_pace_hr.assert_called_once_with(
            ACTIVITY_ID, statistics_only=True
        )
        parsed = json.loads(result[0].text)
        assert parsed["statistics_only"] is True

    @pytest.mark.asyncio
    async def test_defaults_statistics_only_to_false(
        self, mock_db_reader: MagicMock
    ) -> None:
        mock_db_reader.get_splits_pace_hr.return_value = {}
        handler = SplitsHandler(mock_db_reader)

        await handler.handle("get_splits_pace_hr", {"activity_id": ACTIVITY_ID})

        mock_db_reader.get_splits_pace_hr.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )

    @pytest.mark.asyncio
    async def test_returns_none_as_json_null(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_pace_hr.return_value = None
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_pace_hr", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed is None


# -- get_splits_form_metrics tests --------------------------------------------


class TestGetSplitsFormMetrics:
    """Test get_splits_form_metrics handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_form_metrics.return_value = sample_splits_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_form_metrics",
            {"activity_id": ACTIVITY_ID, "statistics_only": False},
        )

        mock_db_reader.get_splits_form_metrics.assert_called_once_with(
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
        mock_db_reader.get_splits_form_metrics.return_value = sample_statistics_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_form_metrics",
            {"activity_id": ACTIVITY_ID, "statistics_only": True},
        )

        mock_db_reader.get_splits_form_metrics.assert_called_once_with(
            ACTIVITY_ID, statistics_only=True
        )
        parsed = json.loads(result[0].text)
        assert parsed["statistics_only"] is True

    @pytest.mark.asyncio
    async def test_returns_empty_dict(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_form_metrics.return_value = {}
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_form_metrics", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed == {}


# -- get_splits_elevation tests -----------------------------------------------


class TestGetSplitsElevation:
    """Test get_splits_elevation handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_elevation.return_value = sample_splits_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
            "get_splits_elevation", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed is None


# -- get_splits_comprehensive tests -------------------------------------------


class TestGetSplitsComprehensive:
    """Test get_splits_comprehensive handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_comprehensive.return_value = sample_splits_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = SplitsHandler(mock_db_reader)

        await handler.handle("get_splits_comprehensive", {"activity_id": ACTIVITY_ID})

        mock_db_reader.get_splits_comprehensive.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )


# -- get_splits_all (DEPRECATED) tests ----------------------------------------


class TestGetSplitsAll:
    """Test get_splits_all handler (deprecated)."""

    @pytest.mark.asyncio
    async def test_returns_data(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_all.return_value = sample_splits_result
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle("get_splits_all", {"activity_id": ACTIVITY_ID})

        mock_db_reader.get_splits_all.assert_called_once_with(
            ACTIVITY_ID, DEFAULT_MAX_OUTPUT_SIZE
        )
        parsed = json.loads(result[0].text)
        assert parsed == sample_splits_result

    @pytest.mark.asyncio
    async def test_logs_deprecation_warning(
        self, mock_db_reader: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_db_reader.get_splits_all.return_value = {}
        handler = SplitsHandler(mock_db_reader)

        with caplog.at_level(
            logging.WARNING, logger="garmin_mcp.handlers.splits_handler"
        ):
            await handler.handle("get_splits_all", {"activity_id": ACTIVITY_ID})

        assert any("DEPRECATED" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_custom_max_output_size(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_all.return_value = {}
        handler = SplitsHandler(mock_db_reader)

        await handler.handle(
            "get_splits_all",
            {"activity_id": ACTIVITY_ID, "max_output_size": 5000},
        )

        mock_db_reader.get_splits_all.assert_called_once_with(ACTIVITY_ID, 5000)

    @pytest.mark.asyncio
    async def test_returns_none_as_json_null(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_all.return_value = None
        handler = SplitsHandler(mock_db_reader)

        result = await handler.handle("get_splits_all", {"activity_id": ACTIVITY_ID})

        parsed = json.loads(result[0].text)
        assert parsed is None


# -- Error handling tests -----------------------------------------------------


class TestErrorHandling:
    """Test error cases."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_value_error(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = SplitsHandler(mock_db_reader)

        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"activity_id": ACTIVITY_ID})
