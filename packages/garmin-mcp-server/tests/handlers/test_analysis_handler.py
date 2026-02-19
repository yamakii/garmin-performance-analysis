"""Tests for AnalysisHandler."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.analysis_handler import AnalysisHandler

# ---------------------------------------------------------------------------
# handles()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandles:
    """Test handles() method for tool name matching."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "insert_section_analysis_dict",
            "get_interval_analysis",
            "detect_form_anomalies_summary",
            "get_form_anomaly_details",
            "analyze_performance_trends",
            "extract_insights",
            "compare_similar_workouts",
        ],
    )
    def test_handles_known_tools(
        self, mock_db_reader: MagicMock, tool_name: str
    ) -> None:
        handler = AnalysisHandler(mock_db_reader)
        assert handler.handles(tool_name) is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = AnalysisHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = AnalysisHandler(mock_db_reader)
        assert handler.handles("") is False


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
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
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
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
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


# ---------------------------------------------------------------------------
# get_interval_analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetIntervalAnalysis:
    """Test _get_interval_analysis via handle()."""

    @pytest.mark.asyncio
    async def test_returns_data(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        expected = {"intervals": [{"type": "work", "pace": 280}]}
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.interval_analysis.IntervalAnalyzer"
        )
        mock_cls.return_value.get_interval_analysis.return_value = expected
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle("get_interval_analysis", {"activity_id": 12345})

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.get_interval_analysis.assert_called_once_with(
            activity_id=12345
        )


# ---------------------------------------------------------------------------
# detect_form_anomalies_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectFormAnomaliesSummary:
    """Test _detect_form_anomalies_summary via handle()."""

    @pytest.mark.asyncio
    async def test_defaults(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        expected = {"anomaly_count": 2, "summary": "ok"}
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.form_anomaly_detector.FormAnomalyDetector"
        )
        mock_cls.return_value.detect_form_anomalies_summary.return_value = expected
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "detect_form_anomalies_summary", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.detect_form_anomalies_summary.assert_called_once_with(
            activity_id=12345, metrics=None, z_threshold=2.0
        )

    @pytest.mark.asyncio
    async def test_with_optional_args(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.form_anomaly_detector.FormAnomalyDetector"
        )
        mock_cls.return_value.detect_form_anomalies_summary.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "detect_form_anomalies_summary",
            {
                "activity_id": 12345,
                "metrics": ["GCT", "VO"],
                "z_threshold": 1.5,
            },
        )

        mock_cls.return_value.detect_form_anomalies_summary.assert_called_once_with(
            activity_id=12345, metrics=["GCT", "VO"], z_threshold=1.5
        )


# ---------------------------------------------------------------------------
# get_form_anomaly_details
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFormAnomalyDetails:
    """Test _get_form_anomaly_details via handle()."""

    @pytest.mark.asyncio
    async def test_minimal_args(self, mock_db_reader: MagicMock, mocker: Any) -> None:
        expected: dict[str, list[str]] = {"details": []}
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.form_anomaly_detector.FormAnomalyDetector"
        )
        mock_cls.return_value.get_form_anomaly_details.return_value = expected
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "get_form_anomaly_details", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data == expected
        call_kwargs = mock_cls.return_value.get_form_anomaly_details.call_args
        assert call_kwargs.kwargs["activity_id"] == 12345
        assert call_kwargs.kwargs["filters"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_with_all_filters(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.form_anomaly_detector.FormAnomalyDetector"
        )
        mock_cls.return_value.get_form_anomaly_details.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "get_form_anomaly_details",
            {
                "activity_id": 12345,
                "anomaly_ids": [1, 2, 3],
                "time_range": [100, 500],
                "metrics": ["GCT"],
                "z_threshold": 3.0,
                "causes": ["fatigue"],
                "limit": 20,
            },
        )

        call_kwargs = mock_cls.return_value.get_form_anomaly_details.call_args.kwargs
        filters = call_kwargs["filters"]
        assert filters["anomaly_ids"] == [1, 2, 3]
        assert filters["time_range"] == (100, 500)
        assert filters["metrics"] == ["GCT"]
        assert filters["min_z_score"] == 3.0
        assert filters["causes"] == ["fatigue"]
        assert filters["limit"] == 20

    @pytest.mark.asyncio
    async def test_time_range_converted_to_tuple(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.form_anomaly_detector.FormAnomalyDetector"
        )
        mock_cls.return_value.get_form_anomaly_details.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "get_form_anomaly_details",
            {"activity_id": 12345, "time_range": [0, 1000]},
        )

        call_kwargs = mock_cls.return_value.get_form_anomaly_details.call_args.kwargs
        assert isinstance(call_kwargs["filters"]["time_range"], tuple)


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
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
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
            activity_type=None,
            temperature_range=None,
            distance_range=None,
        )

    @pytest.mark.asyncio
    async def test_with_range_filters(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer"
        )
        mock_cls.return_value.analyze_metric_trend.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "analyze_performance_trends",
            {
                "metric": "heart_rate",
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "activity_ids": [111],
                "activity_type": "running",
                "temperature_range": [10.0, 25.0],
                "distance_range": [5.0, 15.0],
            },
        )

        call_kwargs = mock_cls.return_value.analyze_metric_trend.call_args.kwargs
        assert call_kwargs["temperature_range"] == (10.0, 25.0)
        assert call_kwargs["distance_range"] == (5.0, 15.0)
        assert call_kwargs["activity_type"] == "running"

    @pytest.mark.asyncio
    async def test_range_lists_converted_to_tuples(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch(
            "garmin_mcp.rag.queries.trends.PerformanceTrendAnalyzer"
        )
        mock_cls.return_value.analyze_metric_trend.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
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
# extract_insights
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractInsights:
    """Test _extract_insights via handle()."""

    @pytest.mark.asyncio
    async def test_with_activity_id(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        expected = {"insights": ["pace improved"]}
        mock_cls = mocker.patch("garmin_mcp.rag.queries.insights.InsightExtractor")
        mock_cls.return_value.extract_insights.return_value = expected
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "extract_insights",
            {"activity_id": 12345, "keywords": ["improvement"]},
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.extract_insights.assert_called_once_with(
            activity_id=12345, keywords=["improvement"], max_tokens=None
        )

    @pytest.mark.asyncio
    async def test_with_activity_id_and_max_tokens(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch("garmin_mcp.rag.queries.insights.InsightExtractor")
        mock_cls.return_value.extract_insights.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "extract_insights",
            {"activity_id": 12345, "keywords": ["pace"], "max_tokens": 500},
        )

        mock_cls.return_value.extract_insights.assert_called_once_with(
            activity_id=12345, keywords=["pace"], max_tokens=500
        )

    @pytest.mark.asyncio
    async def test_search_mode_without_activity_id(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        expected = {"results": [{"activity_id": 111, "match": "text"}]}
        mock_cls = mocker.patch("garmin_mcp.rag.queries.insights.InsightExtractor")
        mock_cls.return_value.search_by_keywords.return_value = expected
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "extract_insights",
            {"keywords": ["improvement"]},
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.search_by_keywords.assert_called_once_with(
            keywords=["improvement"],
            section_types=None,
            limit=10,
            offset=0,
        )

    @pytest.mark.asyncio
    async def test_search_mode_with_pagination(
        self, mock_db_reader: MagicMock, mocker: Any
    ) -> None:
        mock_cls = mocker.patch("garmin_mcp.rag.queries.insights.InsightExtractor")
        mock_cls.return_value.search_by_keywords.return_value = {}
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "extract_insights",
            {
                "keywords": ["pace"],
                "section_types": ["split", "phase"],
                "limit": 5,
                "offset": 10,
            },
        )

        mock_cls.return_value.search_by_keywords.assert_called_once_with(
            keywords=["pace"],
            section_types=["split", "phase"],
            limit=5,
            offset=10,
        )


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
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "compare_similar_workouts", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data == expected
        mock_cls.return_value.find_similar_workouts.assert_called_once_with(
            activity_id=12345,
            pace_tolerance=0.2,
            distance_tolerance=0.2,
            terrain_match=False,
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
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
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
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
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
        handler = AnalysisHandler(mock_db_reader)

        await handler.handle(
            "compare_similar_workouts",
            {
                "activity_id": 12345,
                "pace_tolerance": 0.1,
                "distance_tolerance": 0.15,
                "terrain_match": True,
                "activity_type_filter": "running",
                "date_range": ["2025-10-01", "2025-10-31"],
                "limit": 5,
            },
        )

        mock_cls.return_value.find_similar_workouts.assert_called_once_with(
            activity_id=12345,
            pace_tolerance=0.1,
            distance_tolerance=0.15,
            terrain_match=True,
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
        handler = AnalysisHandler(mock_db_reader)

        result = await handler.handle(
            "compare_similar_workouts", {"activity_id": 12345}
        )

        data = json.loads(result[0].text)
        assert data["date"] == "2025-10-15"


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = AnalysisHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {})
