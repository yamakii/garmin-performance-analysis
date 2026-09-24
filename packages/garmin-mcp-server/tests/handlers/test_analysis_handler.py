"""Tests for the analysis tools (dispatched via the single-source registry)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool

# ---------------------------------------------------------------------------
# registry membership
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolRegistration:
    """Analysis tools are registered in the single-source registry."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "insert_section_analysis_dict",
            "validate_section_json",
            "get_analysis_contract",
            "analyze_performance_trends",
            "compare_similar_workouts",
        ],
    )
    def test_analysis_tool_registered(self, tool_name: str) -> None:
        assert tool_name in ALL_DEFS_BY_NAME

    @pytest.mark.parametrize("tool_name", ["unknown_tool", ""])
    def test_unknown_tool_not_registered(self, tool_name: str) -> None:
        assert tool_name not in ALL_DEFS_BY_NAME


# ---------------------------------------------------------------------------
# insert_section_analysis_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInsertSectionAnalysisDict:
    """Test _insert_section_analysis_dict via handle()."""

    @pytest.mark.asyncio
    async def test_success(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        mock_insert = mocker.patch(
            "garmin_mcp.database.inserters.section_analyses.insert_section_analysis",
            return_value=True,
        )

        result = dispatch_tool(
            mock_db_reader,
            "insert_section_analysis_dict",
            {
                "activity_id": 12345,
                "activity_date": "2025-10-15",
                "section_type": "split",
                "analysis_data": {"rating": "good"},
            },
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["activity_id"] == 12345
        assert data["section_type"] == "split"
        mock_insert.assert_called_once_with(
            activity_id=12345,
            activity_date="2025-10-15",
            section_type="split",
            analysis_data={"rating": "good"},
        )

    @pytest.mark.asyncio
    async def test_failure(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        mocker.patch(
            "garmin_mcp.database.inserters.section_analyses.insert_section_analysis",
            return_value=False,
        )

        result = dispatch_tool(
            mock_db_reader,
            "insert_section_analysis_dict",
            {
                "activity_id": 12345,
                "activity_date": "2025-10-15",
                "section_type": "split",
                "analysis_data": {},
            },
        )

        data = json.loads(result[0].text)
        assert data["success"] is False


# Note: detect_form_anomalies_summary and get_form_anomaly_details were
# relocated to TimeSeriesHandler in the registry rollout (#329); their
# behavioral tests now live in test_time_series_handler.py.


# ---------------------------------------------------------------------------
# analyze_performance_trends
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzePerformanceTrends:
    """Test _analyze_performance_trends via handle()."""

    @pytest.mark.asyncio
    async def test_required_args_only(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        expected = {"trend": "improving", "slope": -1.5}
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer"
        )
        mock_cls.return_value.analyze_metric_trend.return_value = expected

        result = dispatch_tool(
            mock_db_reader,
            "analyze_performance_trends",
            {
                "metric": "pace",
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "activity_ids": [111, 222, 333],
            },
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.analyze_metric_trend.assert_called_once_with(
            metric="pace",
            start_date="2025-10-01",
            end_date="2025-10-31",
            activity_ids=[111, 222, 333],
            temperature_range=None,
            distance_range=None,
        )

    @pytest.mark.asyncio
    async def test_unsupported_metric_returns_error(
        self, mock_db_reader: MagicMock
    ) -> None:
        result = dispatch_tool(
            mock_db_reader,
            "analyze_performance_trends",
            {
                "metric": "distance",
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "activity_ids": [111],
            },
        )

        data = json.loads(result[0].text)
        assert "Unsupported metric: distance" in data["error"]
        assert "ground_contact_time" in data["error"]

    @pytest.mark.asyncio
    async def test_with_range_filters(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer"
        )
        mock_cls.return_value.analyze_metric_trend.return_value = {}

        dispatch_tool(
            mock_db_reader,
            "analyze_performance_trends",
            {
                "metric": "heart_rate",
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "activity_ids": [111],
                "temperature_range": [10.0, 25.0],
                "distance_range": [5.0, 15.0],
            },
        )

        call_kwargs = mock_cls.return_value.analyze_metric_trend.call_args.kwargs
        assert call_kwargs["temperature_range"] == (10.0, 25.0)
        assert call_kwargs["distance_range"] == (5.0, 15.0)
        assert "activity_type" not in call_kwargs

    @pytest.mark.asyncio
    async def test_range_lists_converted_to_tuples(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer"
        )
        mock_cls.return_value.analyze_metric_trend.return_value = {}

        dispatch_tool(
            mock_db_reader,
            "analyze_performance_trends",
            {
                "metric": "pace",
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "activity_ids": [111],
                "temperature_range": [15, 20],
                "distance_range": [5, 10],
            },
        )

        call_kwargs = mock_cls.return_value.analyze_metric_trend.call_args.kwargs
        assert isinstance(call_kwargs["temperature_range"], tuple)
        assert isinstance(call_kwargs["distance_range"], tuple)


# ---------------------------------------------------------------------------
# compare_similar_workouts
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompareSimilarWorkouts:
    """Test _compare_similar_workouts via handle()."""

    @pytest.mark.asyncio
    async def test_defaults(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        expected = {"similar": [{"activity_id": 999, "similarity": 0.95}]}
        mock_cls = mocker.patch("garmin_mcp.rag.queries.comparisons.WorkoutComparator")
        mock_cls.return_value.find_similar_workouts.return_value = expected

        result = dispatch_tool(
            mock_db_reader, "compare_similar_workouts", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.find_similar_workouts.assert_called_once_with(
            activity_id=12345,
            pace_tolerance=0.2,
            distance_tolerance=0.2,
            activity_type_filter=None,
            date_range=None,
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_with_date_range(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch("garmin_mcp.rag.queries.comparisons.WorkoutComparator")
        mock_cls.return_value.find_similar_workouts.return_value = {}

        dispatch_tool(
            mock_db_reader,
            "compare_similar_workouts",
            {
                "activity_id": 12345,
                "date_range": ["2025-10-01", "2025-10-31"],
            },
        )

        call_kwargs = mock_cls.return_value.find_similar_workouts.call_args.kwargs
        assert call_kwargs["date_range"] == ("2025-10-01", "2025-10-31")

    @pytest.mark.asyncio
    async def test_date_range_converted_to_tuple(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch("garmin_mcp.rag.queries.comparisons.WorkoutComparator")
        mock_cls.return_value.find_similar_workouts.return_value = {}

        dispatch_tool(
            mock_db_reader,
            "compare_similar_workouts",
            {"activity_id": 12345, "date_range": ["2025-01-01", "2025-12-31"]},
        )

        call_kwargs = mock_cls.return_value.find_similar_workouts.call_args.kwargs
        assert isinstance(call_kwargs["date_range"], tuple)

    @pytest.mark.asyncio
    async def test_with_all_options(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch("garmin_mcp.rag.queries.comparisons.WorkoutComparator")
        mock_cls.return_value.find_similar_workouts.return_value = {}

        dispatch_tool(
            mock_db_reader,
            "compare_similar_workouts",
            {
                "activity_id": 12345,
                "pace_tolerance": 0.1,
                "distance_tolerance": 0.15,
                "activity_type_filter": "running",
                "date_range": ["2025-10-01", "2025-10-31"],
                "limit": 5,
            },
        )

        mock_cls.return_value.find_similar_workouts.assert_called_once_with(
            activity_id=12345,
            pace_tolerance=0.1,
            distance_tolerance=0.15,
            activity_type_filter="running",
            date_range=("2025-10-01", "2025-10-31"),
            limit=5,
        )

    @pytest.mark.asyncio
    async def test_json_default_str_for_non_serializable(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        """Verify json.dumps(default=str) handles non-serializable types."""
        from datetime import date

        mock_cls = mocker.patch("garmin_mcp.rag.queries.comparisons.WorkoutComparator")
        mock_cls.return_value.find_similar_workouts.return_value = {
            "date": date(2025, 10, 15),
        }

        result = dispatch_tool(
            mock_db_reader, "compare_similar_workouts", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data["date"] == "2025-10-15"


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnknownTool:
    """An unregistered tool name is not dispatchable via the registry."""

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(mock_db_reader, "nonexistent_tool", {})
