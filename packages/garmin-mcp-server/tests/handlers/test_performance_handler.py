"""Tests for PerformanceHandler."""

import json
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.handlers.performance_handler import PerformanceHandler


@pytest.mark.unit
class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_performance_trends(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_performance_trends") is True

    def test_handles_get_weather_data(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_weather_data") is True

    def test_handles_prefetch_activity_context(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("prefetch_activity_context") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        assert handler.handles("") is False


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestPrefetchActivityContext:
    """Test prefetch_activity_context via handle()."""

    @pytest.mark.asyncio
    async def test_returns_full_context(self, mock_db_reader: MagicMock) -> None:
        prefetch_data = {
            "activity_id": 12345,
            "activity_date": "2026-02-16",
            "training_type": "aerobic_base",
            "temperature_c": 7.8,
            "zone_percentages": {"zone1": 5.2, "zone2": 36.8},
            "form_scores": {"gct": {"star_rating": "★★★★★", "score": 4.8}},
            "phase_structure": {"pace_consistency": 0.017},
        }
        handler = PerformanceHandler(mock_db_reader)

        with patch.object(
            PerformanceHandler,
            "_prefetch_activity_context",
            return_value=prefetch_data,
        ):
            result = await handler.handle(
                "prefetch_activity_context", {"activity_id": 12345}
            )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["training_type"] == "aerobic_base"
        assert data["zone_percentages"]["zone1"] == 5.2
        assert data["form_scores"]["gct"]["score"] == 4.8
        assert data["phase_structure"]["pace_consistency"] == 0.017

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_activity(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = PerformanceHandler(mock_db_reader)

        with patch.object(
            PerformanceHandler,
            "_prefetch_activity_context",
            return_value={"error": "Activity 99999 not found"},
        ):
            result = await handler.handle(
                "prefetch_activity_context", {"activity_id": 99999}
            )

        data = json.loads(result[0].text)
        assert "error" in data


@pytest.mark.unit
class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = PerformanceHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {"activity_id": 12345})
