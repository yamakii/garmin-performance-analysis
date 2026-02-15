"""Tests for TimeSeriesHandler."""

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.time_series_handler import TimeSeriesHandler


class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_split_time_series_detail(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = TimeSeriesHandler(mock_db_reader)
        assert handler.handles("get_split_time_series_detail") is True

    def test_handles_get_time_range_detail(self, mock_db_reader: MagicMock) -> None:
        handler = TimeSeriesHandler(mock_db_reader)
        assert handler.handles("get_time_range_detail") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = TimeSeriesHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = TimeSeriesHandler(mock_db_reader)
        assert handler.handles("") is False


class TestGetSplitTimeSeriesDetail:
    """Test get_split_time_series_detail via handle()."""

    @pytest.mark.asyncio
    async def test_required_args_only(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expected = {"activity_id": 12345, "split_number": 3, "data": [1, 2, 3]}
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.get_split_time_series_detail.return_value = (
            expected
        )
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_split_time_series_detail",
            {"activity_id": 12345, "split_number": 3},
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["split_number"] == 3
        mock_extractor_cls.return_value.get_split_time_series_detail.assert_called_once_with(
            activity_id=12345,
            split_number=3,
            metrics=None,
            statistics_only=False,
            detect_anomalies=False,
            z_threshold=2.0,
        )

    @pytest.mark.asyncio
    async def test_all_optional_args(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expected = {"activity_id": 12345, "statistics": {"mean": 150}}
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.get_split_time_series_detail.return_value = (
            expected
        )
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_split_time_series_detail",
            {
                "activity_id": 12345,
                "split_number": 2,
                "metrics": ["heart_rate", "cadence"],
                "statistics_only": True,
                "detect_anomalies": True,
                "z_threshold": 3.0,
            },
        )

        data = json.loads(result[0].text)
        assert data["statistics"]["mean"] == 150
        mock_extractor_cls.return_value.get_split_time_series_detail.assert_called_once_with(
            activity_id=12345,
            split_number=2,
            metrics=["heart_rate", "cadence"],
            statistics_only=True,
            detect_anomalies=True,
            z_threshold=3.0,
        )

    @pytest.mark.asyncio
    async def test_returns_text_content(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.get_split_time_series_detail.return_value = {}
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_split_time_series_detail",
            {"activity_id": 1, "split_number": 1},
        )

        assert len(result) == 1
        assert result[0].type == "text"


class TestGetTimeRangeDetail:
    """Test get_time_range_detail via handle()."""

    @pytest.mark.asyncio
    async def test_required_args_only(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expected = {"activity_id": 12345, "metrics": {"heart_rate": [150, 152]}}
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.extract_metrics.return_value = expected
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_time_range_detail",
            {"activity_id": 12345, "start_time_s": 100, "end_time_s": 500},
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        mock_extractor_cls.return_value.extract_metrics.assert_called_once_with(
            activity_id=12345,
            start_time=100,
            end_time=500,
            metrics=None,
            statistics_only=False,
        )

    @pytest.mark.asyncio
    async def test_with_optional_args(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        expected = {"statistics": {"mean_hr": 155}}
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.extract_metrics.return_value = expected
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_time_range_detail",
            {
                "activity_id": 12345,
                "start_time_s": 0,
                "end_time_s": 3600,
                "metrics": ["heart_rate"],
                "statistics_only": True,
            },
        )

        data = json.loads(result[0].text)
        assert data["statistics"]["mean_hr"] == 155
        mock_extractor_cls.return_value.extract_metrics.assert_called_once_with(
            activity_id=12345,
            start_time=0,
            end_time=3600,
            metrics=["heart_rate"],
            statistics_only=True,
        )

    @pytest.mark.asyncio
    async def test_returns_text_content(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_extractor_cls = mocker.patch(
            "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
        )
        mock_extractor_cls.return_value.extract_metrics.return_value = {}
        handler = TimeSeriesHandler(mock_db_reader)

        result = await handler.handle(
            "get_time_range_detail",
            {"activity_id": 1, "start_time_s": 0, "end_time_s": 100},
        )

        assert len(result) == 1
        assert result[0].type == "text"


class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = TimeSeriesHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"activity_id": 12345})
