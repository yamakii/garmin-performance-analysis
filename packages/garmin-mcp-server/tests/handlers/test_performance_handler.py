"""Tests for the performance tools (dispatched via the single-source registry)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool


@pytest.mark.unit
class TestToolRegistration:
    """Performance tools are registered in the single-source registry."""

    @pytest.mark.parametrize(
        "name",
        ["get_performance_trends", "get_weather_data", "prefetch_activity_context"],
    )
    def test_performance_tool_registered(self, name: str) -> None:
        assert name in ALL_DEFS_BY_NAME


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

        result = dispatch_tool(
            mock_db_reader, "get_performance_trends", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["pace_consistency"]["cv"] == 0.03
        assert data["hr_drift"]["drift_percent"] == 2.5
        mock_db_reader.get_performance_trends.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_returns_none(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_performance_trends.return_value = None

        result = dispatch_tool(
            mock_db_reader, "get_performance_trends", {"activity_id": 99999}
        )

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

        result = dispatch_tool(
            mock_db_reader, "get_weather_data", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data["activity_id"] == 12345
        assert data["temperature_celsius"] == 18.5
        assert data["humidity_percent"] == 65
        mock_db_reader.get_weather_data.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_returns_none(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_weather_data.return_value = None

        result = dispatch_tool(
            mock_db_reader, "get_weather_data", {"activity_id": 99999}
        )

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

        with patch(
            "garmin_mcp.scripts.prefetch_activity_context.prefetch_activity_context",
            return_value=prefetch_data,
        ):
            result = dispatch_tool(
                mock_db_reader, "prefetch_activity_context", {"activity_id": 12345}
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

        with patch(
            "garmin_mcp.scripts.prefetch_activity_context.prefetch_activity_context",
            return_value={"error": "Activity 99999 not found"},
        ):
            result = dispatch_tool(
                mock_db_reader, "prefetch_activity_context", {"activity_id": 99999}
            )

        data = json.loads(result[0].text)
        assert "error" in data


@pytest.mark.unit
class TestUnknownTool:
    """An unregistered tool name is not dispatchable via the registry."""

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(mock_db_reader, "nonexistent_tool", {"activity_id": 12345})
