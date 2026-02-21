"""Tests for PerformanceTrendAnalyzer."""

from unittest.mock import patch

import pytest

from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer


class TestPerformanceTrendAnalyzer:
    """Test PerformanceTrendAnalyzer functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance with mocked DB."""
        with patch("garmin_mcp.rag.queries.trends.GarminDBReader") as mock_reader:
            analyzer = PerformanceTrendAnalyzer()
            analyzer.db_reader = mock_reader.return_value
            return analyzer

    def test_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.db_reader is not None

    def test_analyze_metric_trend_improving(self, analyzer):
        """Test improving pace trend detection."""
        # Mock bulk query: improving (decreasing) pace
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 310.0,
            2: 305.0,
            3: 300.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result is not None
        assert result["metric"] == "pace"
        assert result["trend"] == "improving"
        assert result["slope"] < 0  # Decreasing pace is improving
        assert result["data_points"] == 3
        # Verify single bulk call instead of per-activity calls
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "pace_seconds_per_km"
        )

    def test_analyze_metric_trend_declining(self, analyzer):
        """Test declining pace trend detection."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 305.0,
            3: 310.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "declining"
        assert result["slope"] > 0  # Increasing pace is declining

    def test_analyze_metric_trend_stable(self, analyzer):
        """Test stable trend detection (p-value > 0.05)."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 301.0,
            3: 299.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "stable"

    def test_analyze_metric_trend_insufficient_data(self, analyzer):
        """Test insufficient data handling."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {1: 300.0}

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1],
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 1

    def test_analyze_metric_heart_rate(self, analyzer):
        """Test heart rate trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 155.0,
            2: 152.0,
            3: 150.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="heart_rate",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "heart_rate"
        assert result["slope"] < 0
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "heart_rate"
        )

    def test_analyze_metric_form_metrics(self, analyzer):
        """Test form metrics (GCT) trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 250.0,
            2: 245.0,
            3: 240.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="ground_contact_time",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "ground_contact_time"
        assert result["data_points"] == 3
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "ground_contact_time"
        )

    def test_analyze_metric_elevation(self, analyzer):
        """Test elevation gain trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 100.0,
            2: 120.0,
            3: 140.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="elevation_gain",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "elevation_gain"
        assert result["slope"] > 0
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "elevation_gain"
        )

    def test_analyze_metric_vertical_oscillation(self, analyzer):
        """Test vertical oscillation trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 9.5,
            2: 9.2,
            3: 9.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="vertical_oscillation",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "vertical_oscillation"
        assert result["data_points"] == 3

    def test_analyze_metric_vertical_ratio(self, analyzer):
        """Test vertical ratio trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 8.5,
            2: 8.2,
            3: 8.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="vertical_ratio",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "vertical_ratio"
        assert result["data_points"] == 3

    def test_analyze_metric_cadence(self, analyzer):
        """Test cadence trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 180.0,
            2: 182.0,
            3: 184.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="cadence",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "cadence"
        assert result["data_points"] == 3
        assert result["slope"] > 0  # Increasing cadence

    def test_analyze_metric_power(self, analyzer):
        """Test power trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 250.0,
            2: 255.0,
            3: 260.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="power",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "power"
        assert result["data_points"] == 3
        assert result["slope"] > 0  # Increasing power

    def test_filter_by_temperature_range(self, analyzer):
        """Test temperature range filtering."""
        analyzer.db_reader.get_weather_data.side_effect = [
            {"temperature_c": 15.0},  # Within range
            {"temperature_c": 25.0},  # Outside range
            {"temperature_c": 18.0},  # Within range
        ]
        # Bulk query returns data for filtered activities only
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            3: 305.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
            temperature_range=(10.0, 20.0),
        )

        # Only activities 1 and 3 should be included
        assert result["data_points"] == 2

    def test_filter_by_distance_range(self, analyzer):
        """Test distance range filtering."""

        splits_data = {
            1: {
                "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 300}] * 2
            },  # 2km - outside
            2: {
                "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 305}] * 5
            },  # 5km - within
            3: {
                "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 310}] * 10
            },  # 10km - within
        }

        def mock_get_splits_pace_hr(activity_id):
            return splits_data.get(activity_id, {"splits": []})

        analyzer.db_reader.get_splits_pace_hr.side_effect = mock_get_splits_pace_hr
        # Bulk query returns data for filtered activities (2 and 3)
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            2: 305.0,
            3: 310.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
            distance_range=(5.0, 15.0),
        )

        # Only activities 2 and 3 should be included
        assert result["data_points"] == 2

    def test_unsupported_metric(self, analyzer):
        """Test unsupported metric handling."""
        with pytest.raises(ValueError, match="Unsupported metric"):
            analyzer.analyze_metric_trend(
                metric="invalid_metric",
                start_date="2025-01-01",
                end_date="2025-01-31",
                activity_ids=[1, 2, 3],
            )

    def test_empty_splits_data(self, analyzer):
        """Test handling of empty splits data."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {}

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 0

    def test_missing_activity_in_bulk_result(self, analyzer):
        """Test that missing activities in bulk result are skipped."""
        # Activity 2 has no data
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 310.0,
            3: 300.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["data_points"] == 2

    def test_order_preserved_in_bulk_result(self, analyzer):
        """Test that activity_ids order is preserved for regression."""
        # Return dict in non-sequential order
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            3: 300.0,
            1: 310.0,
            2: 305.0,
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        # Values should be [310, 305, 300] (following activity_ids order)
        assert result["trend"] == "improving"
        assert result["slope"] < 0
