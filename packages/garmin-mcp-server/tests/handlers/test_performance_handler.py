"""Tests for PerformanceHandler."""

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.performance_handler import PerformanceHandler


class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_performance_trends(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_performance_trends") is True

    def test_handles_get_weather_data(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_weather_data") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("") is False


class TestGetPerformanceTrends:
    """Test get_performance_trends via handle()."""

    @pytest.mark.asyncio
    async def test_returns_data(self, mock_db_reader: MagicMock) -> None:
        trends_data = {
            "activity_id": 12345,
            "pace_consistency": {"cv": 0.03, "rating": "consistent"},
            "hr_drift": {"drift_percent": 2.5},
        }
        mock_db_reader.get_performance_trends.return_value = trends_data
        handler = PerformanceHandler(mock_db_reader)

        result = await handler.handle("get_performance_trends", {"activity_id": 12345})

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["pace_consistency"]["cv"] == 0.03
        assert data["hr_drift"]["drift_percent"] == 2.5
        mock_db_reader.get_performance_trends.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_returns_none(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_performance_trends.return_value = None
        handler = PerformanceHandler(mock_db_reader)

        result = await handler.handle("get_performance_trends", {"activity_id": 99999})

        data = json.loads(result[0].text)
        assert data is None


class TestGetWeatherData:
    """Test get_weather_data via handle()."""

    @pytest.mark.asyncio
    async def test_returns_data(self, mock_db_reader: MagicMock) -> None:
        weather_data = {
            "activity_id": 12345,
            "temperature_celsius": 18.5,
            "humidity_percent": 65,
            "wind_speed_mps": 3.2,
        }
        mock_db_reader.get_weather_data.return_value = weather_data
        handler = PerformanceHandler(mock_db_reader)

        result = await handler.handle("get_weather_data", {"activity_id": 12345})

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["temperature_celsius"] == 18.5
        assert data["humidity_percent"] == 65
        mock_db_reader.get_weather_data.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_returns_none(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_weather_data.return_value = None
        handler = PerformanceHandler(mock_db_reader)

        result = await handler.handle("get_weather_data", {"activity_id": 99999})

        data = json.loads(result[0].text)
        assert data is None


class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"activity_id": 12345})
