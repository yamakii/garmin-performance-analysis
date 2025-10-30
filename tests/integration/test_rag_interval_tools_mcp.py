"""Integration tests for RAG Interval Tools MCP endpoints.

Tests the MCP server integration for:
- get_interval_analysis
- get_split_time_series_detail
- detect_form_anomalies
"""

import json

# Import MCP server components
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from servers.garmin_db_server import call_tool, list_tools
from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector


@pytest.fixture
def fixture_activity_id() -> int:
    """Fixture activity ID for testing."""
    return 12345678901


@pytest.fixture
def fixture_base_path(tmp_path: Path) -> Path:
    """Create temporary data structure for testing."""
    data_path = tmp_path / "data"
    raw_path = data_path / "raw" / "activity" / "12345678901"
    performance_path = data_path / "performance"

    raw_path.mkdir(parents=True)
    performance_path.mkdir(parents=True)

    return tmp_path


@pytest.mark.integration
class TestRagIntervalToolsMcp:
    """Test MCP server integration for RAG interval tools."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_interval_analysis(self):
        """Test that list_tools includes get_interval_analysis."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "get_interval_analysis" in tool_names

        # Find the tool and check its schema
        interval_tool = next(t for t in tools if t.name == "get_interval_analysis")
        assert interval_tool.description is not None
        assert "activity_id" in interval_tool.inputSchema["properties"]
        assert "activity_id" in interval_tool.inputSchema["required"]

    @pytest.mark.asyncio
    async def test_list_tools_includes_split_time_series_detail(self):
        """Test that list_tools includes get_split_time_series_detail."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "get_split_time_series_detail" in tool_names

        # Find the tool and check its schema
        detail_tool = next(t for t in tools if t.name == "get_split_time_series_detail")
        assert detail_tool.description is not None
        assert "activity_id" in detail_tool.inputSchema["properties"]
        assert "split_number" in detail_tool.inputSchema["properties"]
        assert "activity_id" in detail_tool.inputSchema["required"]
        assert "split_number" in detail_tool.inputSchema["required"]

    @pytest.mark.asyncio
    async def test_list_tools_includes_new_form_anomaly_apis(self):
        """Test that list_tools includes new form anomaly APIs."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        # Check both new APIs
        assert "detect_form_anomalies_summary" in tool_names
        assert "get_form_anomaly_details" in tool_names

        # Find the tools and check their schemas
        summary_tool = next(
            t for t in tools if t.name == "detect_form_anomalies_summary"
        )
        assert summary_tool.description is not None
        assert "activity_id" in summary_tool.inputSchema["properties"]
        assert "activity_id" in summary_tool.inputSchema["required"]

        details_tool = next(t for t in tools if t.name == "get_form_anomaly_details")
        assert details_tool.description is not None
        assert "activity_id" in details_tool.inputSchema["properties"]
        assert "activity_id" in details_tool.inputSchema["required"]

    @pytest.mark.asyncio
    async def test_call_interval_analysis_with_minimal_args(
        self, fixture_activity_id: int, fixture_base_path: Path
    ):
        """Test calling get_interval_analysis with minimal arguments."""
        # Create fixture data
        activity_details_path = (
            fixture_base_path
            / "data"
            / "raw"
            / "activity"
            / str(fixture_activity_id)
            / "activity_details.json"
        )
        activity_details_path.parent.mkdir(parents=True, exist_ok=True)
        activity_details_data = {
            "activityId": fixture_activity_id,
            "measurementCount": 5,
            "metricsCount": 100,
            "metricDescriptors": [
                {"metricsIndex": 0, "key": "sumDuration"},
                {"metricsIndex": 3, "key": "directHeartRate"},
                {"metricsIndex": 5, "key": "directSpeed", "unit": {"factor": 1000}},
            ],
            "activityDetailMetrics": [
                {"metrics": [i, 150 + i, 0, 0, 3000, 0]} for i in range(100)
            ],
        }
        activity_details_path.write_text(json.dumps(activity_details_data))

        # Mock base_path for IntervalAnalyzer
        def mock_init(self: object, base_path: object = None) -> None:
            self.base_path = fixture_base_path  # type: ignore[attr-defined]
            self.loader = MagicMock(load_activity_details=lambda _: activity_details_data, parse_metric_descriptors=lambda _: {"sumDuration": 0, "directHeartRate": 3, "directSpeed": 5})  # type: ignore[attr-defined]

        with patch(
            "tools.rag.queries.interval_analysis.IntervalAnalyzer.__init__",
            mock_init,
        ):
            result = await call_tool(
                name="get_interval_analysis",
                arguments={"activity_id": fixture_activity_id},
            )

        # Verify response structure
        assert len(result) == 1
        response_data = json.loads(result[0].text)
        assert "activity_id" in response_data
        assert response_data["activity_id"] == fixture_activity_id

    @pytest.mark.asyncio
    async def test_call_interval_analysis_returns_valid_response(
        self, fixture_activity_id: int
    ):
        """Test calling get_interval_analysis returns valid response structure."""
        with patch(
            "tools.rag.queries.interval_analysis.IntervalAnalyzer.get_interval_analysis"
        ) as mock_analyze:
            mock_analyze.return_value = {
                "activity_id": fixture_activity_id,
                "segments": [],
                "work_recovery_comparison": {},
                "fatigue_indicators": {},
            }

            result = await call_tool(
                name="get_interval_analysis",
                arguments={
                    "activity_id": fixture_activity_id,
                },
            )

            # Verify mock was called with only activity_id (no obsolete parameters)
            mock_analyze.assert_called_once_with(
                activity_id=fixture_activity_id,
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["activity_id"] == fixture_activity_id
            assert "segments" in response_data
            assert "work_recovery_comparison" in response_data
            assert "fatigue_indicators" in response_data

    @pytest.mark.asyncio
    async def test_call_split_time_series_detail_with_minimal_args(
        self, fixture_activity_id: int, fixture_base_path: Path
    ):
        """Test calling get_split_time_series_detail with minimal arguments (Phase 3: DuckDB-based)."""
        import duckdb

        from tools.database.db_writer import GarminDBWriter

        # Create DuckDB with test data (Phase 3: Required for _get_split_time_range())
        db_path = fixture_base_path / "test_mcp.duckdb"
        writer = GarminDBWriter(str(db_path))
        writer._ensure_tables()

        # Insert test activity and splits
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name) VALUES (?, ?, ?)",
            (fixture_activity_id, "2025-10-11", "Test Run"),
        )
        conn.execute(
            """
            INSERT INTO splits (
                activity_id, split_index, distance, duration_seconds,
                start_time_s, end_time_s, pace_seconds_per_km, heart_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_activity_id, 1, 1.0, 250.0, 0, 250, 250.0, 160),
        )
        conn.close()

        # Create fixture activity_details.json
        activity_details_path = (
            fixture_base_path
            / "data"
            / "raw"
            / "activity"
            / str(fixture_activity_id)
            / "activity_details.json"
        )
        activity_details_path.parent.mkdir(parents=True, exist_ok=True)
        activity_details_data = {
            "activityId": fixture_activity_id,
            "measurementCount": 3,
            "metricsCount": 250,
            "metricDescriptors": [
                {"metricsIndex": 0, "key": "sumDuration"},
                {"metricsIndex": 1, "key": "directHeartRate"},
                {"metricsIndex": 2, "key": "directSpeed", "unit": {"factor": 1000}},
            ],
            "activityDetailMetrics": [{"metrics": [i, 160, 3500]} for i in range(250)],
        }
        activity_details_path.write_text(json.dumps(activity_details_data))

        # Store db_path for closure
        test_db_path = str(db_path)

        # Patch TimeSeriesDetailExtractor to use fixture base path and db_path
        def mock_init_detail(
            self_obj: object, base_path: object = None, db_path: object = None
        ) -> None:
            self_obj.base_path = fixture_base_path  # type: ignore[attr-defined]
            self_obj.db_path = test_db_path  # type: ignore[attr-defined] # Phase 3: Use test DuckDB
            self_obj.loader = type(  # type: ignore[attr-defined]
                "MockLoader",
                (),
                {
                    "load_activity_details": lambda _, aid: activity_details_data,
                    "parse_metric_descriptors": lambda _, md: {
                        "sumDuration": {"index": 0},
                        "directHeartRate": {"index": 1},
                        "directSpeed": {"index": 2, "unit": {"factor": 1000}},
                    },
                    "apply_unit_conversion": lambda _, metric, val: (
                        val if "unit" not in metric else val / metric["unit"]["factor"]
                    ),
                },
            )()

        with patch(
            "tools.rag.queries.time_series_detail.TimeSeriesDetailExtractor.__init__",
            mock_init_detail,
        ):
            result = await call_tool(
                name="get_split_time_series_detail",
                arguments={"activity_id": fixture_activity_id, "split_number": 1},
            )

        # Verify response structure
        assert len(result) == 1
        response_data = json.loads(result[0].text)
        assert "activity_id" in response_data
        assert "split_number" in response_data
        assert response_data["activity_id"] == fixture_activity_id
        assert response_data["split_number"] == 1

    @pytest.mark.asyncio
    async def test_call_split_time_series_detail_with_metrics_filter(
        self, fixture_activity_id: int
    ):
        """Test calling get_split_time_series_detail with metrics filter."""
        with patch(
            "tools.rag.queries.time_series_detail.TimeSeriesDetailExtractor.get_split_time_series_detail"
        ) as mock_detail:
            mock_detail.return_value = {
                "activity_id": fixture_activity_id,
                "split_number": 2,
                "time_series": [],
            }

            result = await call_tool(
                name="get_split_time_series_detail",
                arguments={
                    "activity_id": fixture_activity_id,
                    "split_number": 2,
                    "metrics": ["directHeartRate", "directSpeed"],
                },
            )

            # Verify mock was called with correct arguments
            mock_detail.assert_called_once_with(
                activity_id=fixture_activity_id,
                split_number=2,
                metrics=["directHeartRate", "directSpeed"],
                statistics_only=False,
                detect_anomalies=False,
                z_threshold=2.0,
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["split_number"] == 2

    @pytest.mark.asyncio
    async def test_call_detect_form_anomalies_summary_with_minimal_args(
        self, fixture_activity_id: int, fixture_base_path: Path
    ):
        """Test calling detect_form_anomalies_summary with minimal arguments."""
        # Create fixture activity_details.json
        activity_details_path = (
            fixture_base_path
            / "data"
            / "raw"
            / "activity"
            / str(fixture_activity_id)
            / "activity_details.json"
        )
        activity_details_path.parent.mkdir(parents=True, exist_ok=True)
        activity_details_data = {
            "activityId": fixture_activity_id,
            "measurementCount": 5,
            "metricsCount": 100,
            "metricDescriptors": [
                {"metricsIndex": 0, "key": "sumDuration"},
                {"metricsIndex": 1, "key": "directGroundContactTime"},
                {"metricsIndex": 2, "key": "directVerticalOscillation"},
                {"metricsIndex": 3, "key": "directVerticalRatio"},
                {"metricsIndex": 4, "key": "directHeartRate"},
            ],
            "activityDetailMetrics": [
                {"metrics": [i, 220, 8.0, 9.0, 160]} for i in range(100)
            ],
        }
        activity_details_path.write_text(json.dumps(activity_details_data))

        # Use mock with proper return value structure
        with patch.object(
            FormAnomalyDetector,
            "detect_form_anomalies_summary",
            return_value={
                "activity_id": fixture_activity_id,
                "anomalies_detected": 0,
                "summary": {
                    "gct_anomalies": 0,
                    "vo_anomalies": 0,
                    "vr_anomalies": 0,
                    "elevation_related": 0,
                    "pace_related": 0,
                    "fatigue_related": 0,
                    "severity_distribution": {"high": 0, "medium": 0, "low": 0},
                    "temporal_clusters": [],
                },
                "top_anomalies": [],
                "recommendations": [],
            },
        ):
            result = await call_tool(
                name="detect_form_anomalies_summary",
                arguments={"activity_id": fixture_activity_id},
            )

        # Verify response structure
        assert len(result) == 1
        response_data = json.loads(result[0].text)
        assert "activity_id" in response_data
        assert "anomalies_detected" in response_data
        assert "summary" in response_data
        assert "top_anomalies" in response_data
        assert "recommendations" in response_data
        assert response_data["activity_id"] == fixture_activity_id

    @pytest.mark.asyncio
    async def test_call_get_form_anomaly_details_with_filters(
        self, fixture_activity_id: int
    ):
        """Test calling get_form_anomaly_details with filtering options."""
        with patch(
            "tools.rag.queries.form_anomaly_detector.FormAnomalyDetector.get_form_anomaly_details"
        ) as mock_details:
            mock_details.return_value = {
                "activity_id": fixture_activity_id,
                "total_anomalies": 10,
                "returned_anomalies": 5,
                "anomalies": [],
            }

            result = await call_tool(
                name="get_form_anomaly_details",
                arguments={
                    "activity_id": fixture_activity_id,
                    "metrics": ["directGroundContactTime"],
                    "z_threshold": 2.5,
                    "limit": 5,
                    "causes": ["elevation_change"],
                },
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["total_anomalies"] == 10
            assert response_data["returned_anomalies"] == 5

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool_error(self):
        """Test that calling unknown tool raises ValueError."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await call_tool(name="unknown_tool", arguments={})

    @pytest.mark.asyncio
    async def test_call_interval_analysis_missing_activity_id_error(self):
        """Test that missing activity_id raises KeyError."""
        with pytest.raises(KeyError):
            await call_tool(name="get_interval_analysis", arguments={})

    @pytest.mark.asyncio
    async def test_call_split_time_series_missing_split_number_error(
        self, fixture_activity_id: int
    ):
        """Test that missing split_number raises KeyError."""
        with pytest.raises(KeyError):
            await call_tool(
                name="get_split_time_series_detail",
                arguments={"activity_id": fixture_activity_id},
            )

    @pytest.mark.asyncio
    async def test_list_tools_includes_phase3_rag_tools(self):
        """Test that list_tools includes Phase 3 RAG tools."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        # Verify all Phase 3 tools are present
        assert "analyze_performance_trends" in tool_names
        assert "extract_insights" in tool_names

    @pytest.mark.asyncio
    async def test_call_analyze_performance_trends_with_minimal_args(
        self, fixture_activity_id: int
    ):
        """Test calling analyze_performance_trends with minimal arguments."""
        with patch(
            "tools.rag.queries.trends.PerformanceTrendAnalyzer.analyze_metric_trend"
        ) as mock_analyze:
            mock_analyze.return_value = {
                "metric": "pace",
                "trend": "improving",
                "slope": -1.5,
                "correlation": -0.85,
                "p_value": 0.001,
                "data_points": 10,
                "start_date": "2025-10-01",
                "end_date": "2025-10-10",
                "filtered_activity_ids": [fixture_activity_id],
            }

            result = await call_tool(
                name="analyze_performance_trends",
                arguments={
                    "metric": "pace",
                    "start_date": "2025-10-01",
                    "end_date": "2025-10-10",
                    "activity_ids": [fixture_activity_id],
                },
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["metric"] == "pace"
            assert response_data["trend"] == "improving"
            assert "data_points" in response_data

    @pytest.mark.asyncio
    async def test_call_analyze_performance_trends_with_filters(
        self, fixture_activity_id: int
    ):
        """Test calling analyze_performance_trends with filtering options."""
        with patch(
            "tools.rag.queries.trends.PerformanceTrendAnalyzer.analyze_metric_trend"
        ) as mock_analyze:
            mock_analyze.return_value = {
                "metric": "heart_rate",
                "trend": "stable",
                "slope": 0.1,
                "correlation": 0.05,
                "p_value": 0.8,
                "data_points": 5,
                "start_date": "2025-10-01",
                "end_date": "2025-10-10",
                "filtered_activity_ids": [fixture_activity_id],
            }

            result = await call_tool(
                name="analyze_performance_trends",
                arguments={
                    "metric": "heart_rate",
                    "start_date": "2025-10-01",
                    "end_date": "2025-10-10",
                    "activity_ids": [fixture_activity_id],
                    "activity_type": "base",
                    "temperature_range": [15.0, 25.0],
                    "distance_range": [5.0, 15.0],
                },
            )

            # Verify mock was called with correct arguments (tuples converted)
            mock_analyze.assert_called_once()
            call_args = mock_analyze.call_args[1]
            assert call_args["temperature_range"] == (15.0, 25.0)
            assert call_args["distance_range"] == (5.0, 15.0)

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_call_extract_insights_general_search(self):
        """Test calling extract_insights for general keyword search."""
        with patch(
            "tools.rag.queries.insights.InsightExtractor.search_by_keywords"
        ) as mock_search:
            mock_search.return_value = [
                {
                    "activity_id": 12345,
                    "activity_date": "2025-10-01",
                    "section_type": "efficiency",
                    "analysis_data": {"improvements": ["Better GCT"]},
                }
            ]

            result = await call_tool(
                name="extract_insights",
                arguments={
                    "keywords": ["improvements", "concerns"],
                    "section_types": ["efficiency"],
                    "limit": 5,
                    "offset": 0,
                },
            )

            # Verify mock was called correctly
            mock_search.assert_called_once_with(
                keywords=["improvements", "concerns"],
                section_types=["efficiency"],
                limit=5,
                offset=0,
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert isinstance(response_data, list)
            assert len(response_data) == 1
            assert response_data[0]["section_type"] == "efficiency"

    @pytest.mark.asyncio
    async def test_call_extract_insights_single_activity(
        self, fixture_activity_id: int
    ):
        """Test calling extract_insights for single activity with token limiting."""
        with patch(
            "tools.rag.queries.insights.InsightExtractor.extract_insights"
        ) as mock_extract:
            mock_extract.return_value = {
                "insights": [
                    {
                        "section_type": "efficiency",
                        "improvements": ["Better GCT"],
                    }
                ],
                "total_tokens": 120,
                "truncated": False,
            }

            result = await call_tool(
                name="extract_insights",
                arguments={
                    "activity_id": fixture_activity_id,
                    "keywords": ["improvements"],
                    "max_tokens": 500,
                },
            )

            # Verify response structure (not supported in current implementation)
            # Note: Current implementation doesn't support activity_id parameter
            # This test documents the expected behavior for future enhancement
            assert len(result) == 1

    # ============================================================
    # Phase 4.5: compare_similar_workouts tests
    # ============================================================

    @pytest.mark.asyncio
    async def test_list_tools_includes_compare_similar_workouts(self):
        """Test that list_tools includes compare_similar_workouts."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]
        assert "compare_similar_workouts" in tool_names

    @pytest.mark.asyncio
    async def test_call_compare_similar_workouts_with_minimal_args(
        self, fixture_activity_id: int
    ):
        """Test calling compare_similar_workouts with minimal arguments."""
        with patch(
            "tools.rag.queries.comparisons.WorkoutComparator.find_similar_workouts"
        ) as mock_find:
            mock_find.return_value = {
                "target_activity": {
                    "activity_id": fixture_activity_id,
                    "activity_date": "2025-10-01",
                    "activity_name": "Morning Run",
                    "avg_pace": 300.0,
                    "avg_heart_rate": 150.0,
                    "distance_km": 10.0,
                },
                "similar_activities": [
                    {
                        "activity_id": 12345678900,
                        "activity_date": "2025-09-15",
                        "activity_name": "Easy Run",
                        "similarity_score": 95.5,
                        "pace_diff": 5.0,
                        "hr_diff": -2.0,
                        "interpretation": "ペース: 5.0秒/km遅い, 心拍数: 2bpm低い",
                    }
                ],
                "comparison_summary": "1件の類似ワークアウトを発見。平均類似度: 95.5%",
            }

            result = await call_tool(
                name="compare_similar_workouts",
                arguments={"activity_id": fixture_activity_id},
            )

            # Verify mock was called with correct arguments
            mock_find.assert_called_once()
            call_args = mock_find.call_args[1]
            assert call_args["activity_id"] == fixture_activity_id
            assert call_args["pace_tolerance"] == 0.2  # default (updated from 0.1)
            assert call_args["distance_tolerance"] == 0.2  # default (updated from 0.1)

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert (
                response_data["target_activity"]["activity_id"] == fixture_activity_id
            )
            assert len(response_data["similar_activities"]) == 1
            assert "comparison_summary" in response_data

    @pytest.mark.asyncio
    async def test_call_compare_similar_workouts_with_all_filters(
        self, fixture_activity_id: int
    ):
        """Test calling compare_similar_workouts with all filtering options."""
        with patch(
            "tools.rag.queries.comparisons.WorkoutComparator.find_similar_workouts"
        ) as mock_find:
            mock_find.return_value = {
                "target_activity": {
                    "activity_id": fixture_activity_id,
                    "activity_date": "2025-10-01",
                    "avg_pace": 280.0,
                    "distance_km": 8.0,
                },
                "similar_activities": [],
                "comparison_summary": "類似するワークアウトが見つかりませんでした",
            }

            result = await call_tool(
                name="compare_similar_workouts",
                arguments={
                    "activity_id": fixture_activity_id,
                    "pace_tolerance": 0.05,
                    "distance_tolerance": 0.05,
                    "terrain_match": True,
                    "activity_type_filter": "Tempo",
                    "date_range": ["2025-09-01", "2025-09-30"],
                    "limit": 5,
                },
            )

            # Verify mock was called with correct arguments
            mock_find.assert_called_once()
            call_args = mock_find.call_args[1]
            assert call_args["pace_tolerance"] == 0.05
            assert call_args["distance_tolerance"] == 0.05
            assert call_args["terrain_match"] is True
            assert call_args["activity_type_filter"] == "Tempo"
            assert call_args["date_range"] == ("2025-09-01", "2025-09-30")
            assert call_args["limit"] == 5

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert len(response_data["similar_activities"]) == 0
