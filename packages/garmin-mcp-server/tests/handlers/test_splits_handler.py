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
        [
            "get_splits_pace_hr",
            "get_splits_form_metrics",
            "get_splits_elevation",
            "get_splits_comprehensive",
        ],
    )
    def test_splits_tool_registered(self, tool_name: str) -> None:
        assert tool_name in ALL_DEFS_BY_NAME

    @pytest.mark.parametrize(
        "tool_name",
        ["unknown_tool", "", "get_splits_pace_hr_v2"],
    )
    def test_unknown_tool_not_registered(self, tool_name: str) -> None:
        assert tool_name not in ALL_DEFS_BY_NAME


# -- get_splits_pace_hr tests -------------------------------------------------


@pytest.mark.unit
class TestGetSplitsPaceHr:
    """Test get_splits_pace_hr handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_pace_hr.return_value = sample_splits_result

        result = dispatch_tool(
            mock_db_reader,
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

        result = dispatch_tool(
            mock_db_reader,
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

        dispatch_tool(
            mock_db_reader, "get_splits_pace_hr", {"activity_id": ACTIVITY_ID}
        )

        mock_db_reader.get_splits_pace_hr.assert_called_once_with(
            ACTIVITY_ID, statistics_only=False
        )

    @pytest.mark.asyncio
    async def test_returns_none_as_json_null(self, mock_db_reader: MagicMock) -> None:
        mock_db_reader.get_splits_pace_hr.return_value = None

        result = dispatch_tool(
            mock_db_reader, "get_splits_pace_hr", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed is None


# -- get_splits_form_metrics tests --------------------------------------------


@pytest.mark.unit
class TestGetSplitsFormMetrics:
    """Test get_splits_form_metrics handler."""

    @pytest.mark.asyncio
    async def test_returns_data_statistics_only_false(
        self,
        mock_db_reader: MagicMock,
        sample_splits_result: dict[str, Any],
    ) -> None:
        mock_db_reader.get_splits_form_metrics.return_value = sample_splits_result

        result = dispatch_tool(
            mock_db_reader,
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

        result = dispatch_tool(
            mock_db_reader,
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

        result = dispatch_tool(
            mock_db_reader, "get_splits_form_metrics", {"activity_id": ACTIVITY_ID}
        )

        parsed = json.loads(result[0].text)
        assert parsed == {}


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


# ---------------------------------------------------------------------------
# get_interval_analysis (relocated from AnalysisHandler in #329)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetIntervalAnalysis:
    """Test get_interval_analysis via handle()."""

    @pytest.mark.asyncio
    async def test_returns_data(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        expected = {"intervals": [{"type": "work", "pace": 280}]}
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.interval_analysis.IntervalAnalyzer"
        )
        mock_cls.return_value.get_interval_analysis.return_value = expected

        result = dispatch_tool(
            mock_db_reader, "get_interval_analysis", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.get_interval_analysis.assert_called_once_with(
            activity_id=12345
        )

    def test_interval_analysis_registered(self) -> None:
        assert "get_interval_analysis" in ALL_DEFS_BY_NAME
