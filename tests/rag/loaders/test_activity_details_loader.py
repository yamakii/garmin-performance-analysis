"""Tests for ActivityDetailsLoader."""

import json
from typing import Any

import pytest

from tools.rag.loaders.activity_details_loader import ActivityDetailsLoader


class TestActivityDetailsLoader:
    """Test suite for ActivityDetailsLoader class."""

    def test_load_activity_details_success(self, fixture_base_path, dummy_activity_id):
        """Test successful loading of activity_details.json."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)

        assert result is not None
        assert result["activityId"] == dummy_activity_id
        assert "metricDescriptors" in result
        assert "activityDetailMetrics" in result

    def test_load_activity_details_file_not_found(self):
        """Test error handling when file doesn't exist."""
        loader = ActivityDetailsLoader()
        activity_id = 99999999999

        with pytest.raises(FileNotFoundError):
            loader.load_activity_details(activity_id)

    def test_load_activity_details_invalid_json(self, tmp_path):
        """Test error handling for invalid JSON."""
        # Create a temporary invalid JSON file
        activity_id = 12345678901
        activity_dir = tmp_path / "data" / "raw" / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        invalid_json_file = activity_dir / "activity_details.json"
        invalid_json_file.write_text("{ invalid json }")

        loader = ActivityDetailsLoader(base_path=tmp_path / "data")

        with pytest.raises(json.JSONDecodeError):
            loader.load_activity_details(activity_id)

    def test_parse_metric_descriptors(self, fixture_base_path, dummy_activity_id):
        """Test parsing of metric descriptors into a mapping."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)
        metric_map = loader.parse_metric_descriptors(result["metricDescriptors"])

        # Check metrics from fixture data
        assert "directHeartRate" in metric_map
        assert metric_map["directHeartRate"]["index"] == 0
        assert metric_map["directHeartRate"]["unit"] == "bpm"
        assert metric_map["directHeartRate"]["factor"] == 1.0

        assert "directSpeed" in metric_map
        assert metric_map["directSpeed"]["index"] == 1
        assert metric_map["directSpeed"]["factor"] == 0.1

    def test_extract_time_series_full_range(self, fixture_base_path, dummy_activity_id):
        """Test time series extraction for full activity."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)
        metrics = result["activityDetailMetrics"]

        # Extract speed metric (index 1) - 10 measurements in fixture
        time_series = loader.extract_time_series(
            metrics=metrics, metric_index=1, start_index=0, end_index=None
        )

        assert len(time_series) == 10
        assert time_series[0] == 30  # First speed value from fixture

    def test_extract_time_series_partial_range(
        self, fixture_base_path, dummy_activity_id
    ):
        """Test time series extraction for a specific range."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)
        metrics = result["activityDetailMetrics"]

        # Extract heart rate metric (index 0) for measurements 1-3
        time_series = loader.extract_time_series(
            metrics=metrics, metric_index=0, start_index=1, end_index=3
        )

        assert len(time_series) == 2
        assert time_series == [125, 130]  # HR values from fixture

    def test_apply_unit_conversion(self, fixture_base_path, dummy_activity_id):
        """Test unit conversion with factor application."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)
        metric_map = loader.parse_metric_descriptors(result["metricDescriptors"])

        # Test conversion for directSpeed (factor 0.1)
        raw_value = 30.0
        converted = loader.apply_unit_conversion(
            metric_info=metric_map["directSpeed"], value=raw_value
        )

        # 30.0 / 0.1 = 300.0 m/s
        assert converted == 300.0

    def test_apply_unit_conversion_no_factor(
        self, fixture_base_path, dummy_activity_id
    ):
        """Test unit conversion when factor is 1.0."""
        loader = ActivityDetailsLoader(base_path=fixture_base_path)

        result = loader.load_activity_details(dummy_activity_id)
        metric_map = loader.parse_metric_descriptors(result["metricDescriptors"])

        # Test conversion for directHeartRate (factor 1.0)
        raw_value = 120.0
        converted = loader.apply_unit_conversion(
            metric_info=metric_map["directHeartRate"], value=raw_value
        )

        # No conversion needed
        assert converted == 120.0

    def test_handle_null_values_in_metrics(self):
        """Test handling of null values in metric arrays."""
        loader = ActivityDetailsLoader()

        # Create test data with null values
        metrics: list[dict[str, list[Any]]] = [
            {"metrics": [100.0, None, 130.0]},
            {"metrics": [200.0, 175.0, None]},
            {"metrics": [300.0, 180.0, 140.0]},
        ]

        time_series = loader.extract_time_series(
            metrics=metrics, metric_index=1, start_index=0, end_index=None
        )

        # None values should be preserved
        assert len(time_series) == 3
        assert time_series[0] is None
        assert time_series[1] == 175.0
        assert time_series[2] == 180.0

    def test_custom_base_path(self, tmp_path):
        """Test ActivityDetailsLoader with custom base path."""
        # Create test data in custom location
        activity_id = 12345678901
        activity_dir = tmp_path / "data" / "raw" / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        test_data = {
            "activityId": activity_id,
            "metricDescriptors": [],
            "activityDetailMetrics": [],
        }

        json_file = activity_dir / "activity_details.json"
        json_file.write_text(json.dumps(test_data))

        loader = ActivityDetailsLoader(base_path=tmp_path / "data")
        result = loader.load_activity_details(activity_id)

        assert result["activityId"] == activity_id
