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
    async def test_list_tools_includes_detect_form_anomalies(self):
        """Test that list_tools includes detect_form_anomalies."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "detect_form_anomalies" in tool_names

        # Find the tool and check its schema
        anomaly_tool = next(t for t in tools if t.name == "detect_form_anomalies")
        assert anomaly_tool.description is not None
        assert "activity_id" in anomaly_tool.inputSchema["properties"]
        assert "activity_id" in anomaly_tool.inputSchema["required"]

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
            "INSERT INTO activities (activity_id, date, activity_name) VALUES (?, ?, ?)",
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
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["split_number"] == 2

    @pytest.mark.asyncio
    async def test_call_detect_form_anomalies_with_minimal_args(
        self, fixture_activity_id: int, fixture_base_path: Path
    ):
        """Test calling detect_form_anomalies with minimal arguments."""
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
            "detect_form_anomalies",
            return_value={
                "activity_id": fixture_activity_id,
                "anomalies_detected": 0,
                "anomalies": [],
            },
        ):
            result = await call_tool(
                name="detect_form_anomalies",
                arguments={"activity_id": fixture_activity_id},
            )

        # Verify response structure
        assert len(result) == 1
        response_data = json.loads(result[0].text)
        assert "activity_id" in response_data
        assert "anomalies_detected" in response_data
        assert response_data["activity_id"] == fixture_activity_id

    @pytest.mark.asyncio
    async def test_call_detect_form_anomalies_with_all_args(
        self, fixture_activity_id: int
    ):
        """Test calling detect_form_anomalies with all optional arguments."""
        with patch(
            "tools.rag.queries.form_anomaly_detector.FormAnomalyDetector.detect_form_anomalies"
        ) as mock_detect:
            mock_detect.return_value = {
                "activity_id": fixture_activity_id,
                "anomalies_detected": 0,
                "anomalies": [],
            }

            result = await call_tool(
                name="detect_form_anomalies",
                arguments={
                    "activity_id": fixture_activity_id,
                    "metrics": ["directGroundContactTime"],
                    "z_threshold": 2.5,
                    "context_window": 45,
                },
            )

            # Verify mock was called with correct arguments
            mock_detect.assert_called_once_with(
                activity_id=fixture_activity_id,
                metrics=["directGroundContactTime"],
                z_threshold=2.5,
                context_window=45,
            )

            # Verify response structure
            assert len(result) == 1
            response_data = json.loads(result[0].text)
            assert response_data["anomalies_detected"] == 0

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
