"""Tests for PerformanceTrendAnalyzer."""

from unittest.mock import patch

import pytest

from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer


@pytest.mark.integration
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
        # Mock pace data: improving (decreasing) pace
        analyzer.db_reader.get_splits_pace_hr.side_effect = [
            {"splits": [{"avg_pace_seconds_per_km": 310}]},
            {"splits": [{"avg_pace_seconds_per_km": 305}]},
            {"splits": [{"avg_pace_seconds_per_km": 300}]},
        ]

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

    def test_analyze_metric_trend_declining(self, analyzer):
        """Test declining pace trend detection."""
        # Mock pace data: declining (increasing) pace
        analyzer.db_reader.get_splits_pace_hr.side_effect = [
            {"splits": [{"avg_pace_seconds_per_km": 300}]},
            {"splits": [{"avg_pace_seconds_per_km": 305}]},
            {"splits": [{"avg_pace_seconds_per_km": 310}]},
        ]

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
        # Mock pace data: random variation
        analyzer.db_reader.get_splits_pace_hr.side_effect = [
            {"splits": [{"avg_pace_seconds_per_km": 300}]},
            {"splits": [{"avg_pace_seconds_per_km": 301}]},
            {"splits": [{"avg_pace_seconds_per_km": 299}]},
        ]

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "stable"

    def test_analyze_metric_trend_insufficient_data(self, analyzer):
        """Test insufficient data handling."""
        # Mock one activity with valid data
        analyzer.db_reader.get_splits_pace_hr.return_value = {
            "splits": [{"avg_pace_seconds_per_km": 300}]
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1],  # Only one activity
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 1

    def test_analyze_metric_heart_rate(self, analyzer):
        """Test heart rate trend analysis."""
        # Mock HR data: improving (decreasing) HR
        analyzer.db_reader.get_splits_pace_hr.side_effect = [
            {"splits": [{"avg_heart_rate": 155}]},
            {"splits": [{"avg_heart_rate": 152}]},
            {"splits": [{"avg_heart_rate": 150}]},
        ]

        result = analyzer.analyze_metric_trend(
            metric="heart_rate",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "heart_rate"
        assert result["slope"] < 0

    def test_analyze_metric_form_metrics(self, analyzer):
        """Test form metrics (GCT, VO, VR) trend analysis."""
        # Mock GCT data
        analyzer.db_reader.get_splits_form_metrics.side_effect = [
            {"splits": [{"ground_contact_time_ms": 250}]},
            {"splits": [{"ground_contact_time_ms": 245}]},
            {"splits": [{"ground_contact_time_ms": 240}]},
        ]

        result = analyzer.analyze_metric_trend(
            metric="ground_contact_time",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "ground_contact_time"
        assert result["data_points"] == 3

    def test_analyze_metric_elevation(self, analyzer):
        """Test elevation gain trend analysis."""
        # Mock elevation data
        analyzer.db_reader.get_splits_elevation.side_effect = [
            {"splits": [{"elevation_gain_m": 100}]},
            {"splits": [{"elevation_gain_m": 120}]},
            {"splits": [{"elevation_gain_m": 140}]},
        ]

        result = analyzer.analyze_metric_trend(
            metric="elevation_gain",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "elevation_gain"
        assert result["slope"] > 0

    def test_analyze_metric_vertical_oscillation(self, analyzer):
        """Test vertical oscillation trend analysis."""
        # Mock VO data
        analyzer.db_reader.get_splits_form_metrics.side_effect = [
            {
                "splits": [
                    {
                        "vertical_oscillation_cm": 9.5,
                        "ground_contact_time_ms": None,
                        "vertical_ratio_percent": None,
                    }
                ]
            },
            {
                "splits": [
                    {
                        "vertical_oscillation_cm": 9.2,
                        "ground_contact_time_ms": None,
                        "vertical_ratio_percent": None,
                    }
                ]
            },
            {
                "splits": [
                    {
                        "vertical_oscillation_cm": 9.0,
                        "ground_contact_time_ms": None,
                        "vertical_ratio_percent": None,
                    }
                ]
            },
        ]

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
        # Mock VR data
        analyzer.db_reader.get_splits_form_metrics.side_effect = [
            {
                "splits": [
                    {
                        "vertical_ratio_percent": 8.5,
                        "ground_contact_time_ms": None,
                        "vertical_oscillation_cm": None,
                    }
                ]
            },
            {
                "splits": [
                    {
                        "vertical_ratio_percent": 8.2,
                        "ground_contact_time_ms": None,
                        "vertical_oscillation_cm": None,
                    }
                ]
            },
            {
                "splits": [
                    {
                        "vertical_ratio_percent": 8.0,
                        "ground_contact_time_ms": None,
                        "vertical_oscillation_cm": None,
                    }
                ]
            },
        ]

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
        # Mock cadence data
        analyzer.db_reader.get_splits_all.side_effect = [
            {"splits": [{"cadence": 180, "power": None}]},
            {"splits": [{"cadence": 182, "power": None}]},
            {"splits": [{"cadence": 184, "power": None}]},
        ]

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
        # Mock power data
        analyzer.db_reader.get_splits_all.side_effect = [
            {"splits": [{"power": 250, "cadence": None}]},
            {"splits": [{"power": 255, "cadence": None}]},
            {"splits": [{"power": 260, "cadence": None}]},
        ]

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
        # Mock weather data
        analyzer.db_reader.get_weather_data.side_effect = [
            {"temperature_c": 15.0},  # Within range
            {"temperature_c": 25.0},  # Outside range
            {"temperature_c": 18.0},  # Within range
        ]

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
            temperature_range=(10.0, 20.0),
        )

        # Only activities 1 and 3 should be included
        assert result["data_points"] <= 2

    def test_filter_by_distance_range(self, analyzer):
        """Test distance range filtering."""

        def mock_get_splits_pace_hr(activity_id):
            # First call: distance filtering
            # Second call: metric extraction
            if activity_id == 1:  # noqa: SIM116
                return {
                    "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 300}] * 2
                }  # 2km - outside
            elif activity_id == 2:
                return {
                    "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 305}] * 5
                }  # 5km - within
            elif activity_id == 3:
                return {
                    "splits": [{"distance_km": 1.0, "avg_pace_seconds_per_km": 310}]
                    * 10
                }  # 10km - within
            return {"splits": []}

        analyzer.db_reader.get_splits_pace_hr.side_effect = mock_get_splits_pace_hr

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
        # Mock empty splits
        analyzer.db_reader.get_splits_pace_hr.return_value = {"splits": []}

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 0
