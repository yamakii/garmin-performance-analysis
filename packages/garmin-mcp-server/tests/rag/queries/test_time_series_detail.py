"""Test suite for TimeSeriesDetailExtractor.

This module tests the time series detail extraction functionality including:
- Split number to time range conversion
- Second-by-second metric extraction
- Statistical calculations (mean, std, min, max)
- Anomaly detection within splits
"""

import pytest

from garmin_mcp.rag.queries.time_series_detail import TimeSeriesDetailExtractor


@pytest.fixture
def extractor():
    """Create TimeSeriesDetailExtractor instance for testing."""
    return TimeSeriesDetailExtractor()


@pytest.mark.unit
def test_split_to_time_range_conversion(extractor: TimeSeriesDetailExtractor):
    """Test converting split number (1-based) to time range.

    Expected behavior:
    - Split 1 should map to start_time_s=0, end_time_s from DuckDB
    - Split N should use start/end times from DuckDB splits table
    - Invalid split numbers should raise ValueError
    """
    # Mock DuckDB splits data
    splits_data = [
        {"split_index": 0, "start_time_s": 0, "end_time_s": 280},
        {"split_index": 1, "start_time_s": 280, "end_time_s": 560},
        {"split_index": 2, "start_time_s": 560, "end_time_s": 840},
    ]

    # Test split 1 (index 0)
    start, end = extractor._split_to_time_range(1, splits_data)
    assert start == 0
    assert end == 280

    # Test split 2 (index 1)
    start, end = extractor._split_to_time_range(2, splits_data)
    assert start == 280
    assert end == 560

    # Test invalid split number
    with pytest.raises(ValueError):
        extractor._split_to_time_range(0, splits_data)  # Split numbers are 1-based

    with pytest.raises(ValueError):
        extractor._split_to_time_range(10, splits_data)  # Out of range


@pytest.mark.unit
def test_extract_metrics_from_time_range(
    extractor: TimeSeriesDetailExtractor, fixture_base_path, dummy_activity_id
):
    """Test extracting second-by-second metrics for specified time range.

    Expected behavior:
    - Should extract metrics for each second in the time range
    - Should apply unit conversions correctly
    - Should handle missing metrics gracefully
    - Should return structured data with timestamps
    """
    # Use fixture-based extractor
    extractor_with_fixture = TimeSeriesDetailExtractor(base_path=fixture_base_path)

    start_time = 0
    end_time = 60  # First 60 seconds
    metrics = ["heart_rate", "speed", "cadence"]

    result = extractor_with_fixture.extract_metrics(
        dummy_activity_id, start_time, end_time, metrics
    )

    # Check result structure
    assert "activity_id" in result
    assert "time_range" in result
    assert "metrics" in result
    assert "time_series" in result

    # Check time range
    assert result["time_range"]["start_time_s"] == start_time
    assert result["time_range"]["end_time_s"] == end_time

    # Check metrics list
    assert set(result["metrics"]) == set(metrics)

    # Check time series data
    assert len(result["time_series"]) > 0  # Should have data points
    for data_point in result["time_series"]:
        assert "timestamp_s" in data_point
        # Metrics might be None if not available in fixture


@pytest.mark.unit
def test_calculate_statistics(extractor: TimeSeriesDetailExtractor):
    """Test statistical calculations on time series data.

    Expected behavior:
    - Calculate mean, std, min, max for each metric
    - Handle missing values (None) gracefully
    - Return statistics in structured format
    """
    time_series_data = [
        {"timestamp_s": 0, "heart_rate": 150, "speed": 3.5, "cadence": 180},
        {"timestamp_s": 1, "heart_rate": 152, "speed": 3.6, "cadence": 182},
        {"timestamp_s": 2, "heart_rate": 154, "speed": 3.7, "cadence": 184},
        {"timestamp_s": 3, "heart_rate": 156, "speed": 3.8, "cadence": 186},
        {"timestamp_s": 4, "heart_rate": 158, "speed": 3.9, "cadence": 188},
    ]

    metrics = ["heart_rate", "speed", "cadence"]
    stats = extractor.calculate_statistics(time_series_data, metrics)

    # Check structure
    assert "heart_rate" in stats
    assert "speed" in stats
    assert "cadence" in stats

    # Check HR statistics
    hr_stats = stats["heart_rate"]
    assert "mean" in hr_stats
    assert "std" in hr_stats
    assert "min" in hr_stats
    assert "max" in hr_stats

    # Verify values
    assert hr_stats["mean"] == pytest.approx(154.0)  # (150+152+154+156+158)/5
    assert hr_stats["min"] == 150
    assert hr_stats["max"] == 158
    assert hr_stats["std"] > 0


@pytest.mark.unit
def test_detect_anomalies_within_split(extractor: TimeSeriesDetailExtractor):
    """Test anomaly detection within a split using z-score.

    Expected behavior:
    - Detect data points that deviate significantly from mean
    - Use configurable z-score threshold (default: 2.0)
    - Return anomaly timestamps and values
    - Identify which metrics are anomalous
    """
    # Create time series with one clear anomaly
    time_series_data = [
        {"timestamp_s": i, "heart_rate": 150 + i}
        for i in range(20)  # HR: 150-169 (normal progression)
    ]
    # Add anomaly at timestamp 10
    time_series_data[10]["heart_rate"] = 200  # Sudden spike

    anomalies = extractor.detect_anomalies(
        time_series_data, metrics=["heart_rate"], z_threshold=2.0
    )

    # Should detect anomaly
    assert len(anomalies) > 0

    # Check anomaly structure
    first_anomaly = anomalies[0]
    assert "timestamp_s" in first_anomaly
    assert "metric" in first_anomaly
    assert "value" in first_anomaly
    assert "z_score" in first_anomaly

    # Verify anomaly detection
    assert first_anomaly["timestamp_s"] == 10
    assert first_anomaly["metric"] == "heart_rate"
    assert first_anomaly["value"] == 200
    assert abs(first_anomaly["z_score"]) > 2.0


@pytest.mark.unit
def test_default_metrics_selection(
    extractor: TimeSeriesDetailExtractor, fixture_base_path, dummy_activity_id
):
    """Test default metrics selection when none specified.

    Expected behavior:
    - If metrics parameter is None/empty, use default set
    - Default set should include: heart_rate, speed, cadence, power,
      vertical_oscillation, ground_contact_time, vertical_ratio
    """
    # Use fixture-based extractor
    extractor_with_fixture = TimeSeriesDetailExtractor(base_path=fixture_base_path)

    start_time = 0
    end_time = 10

    result = extractor_with_fixture.extract_metrics(
        dummy_activity_id, start_time, end_time, metrics=None
    )

    # Should have default metrics
    expected_defaults = [
        "heart_rate",
        "speed",
        "cadence",
        "power",
        "vertical_oscillation",
        "ground_contact_time",
        "vertical_ratio",
    ]

    assert "metrics" in result
    for metric in expected_defaults:
        assert metric in result["metrics"]


@pytest.mark.integration
def test_split_time_series_detail_full_workflow(
    extractor: TimeSeriesDetailExtractor, fixture_base_path, dummy_activity_id
):
    """Integration test: Extract time series detail for a specific split.

    Tests the full workflow:
    1. Convert split number to time range (using mock data)
    2. Extract second-by-second metrics
    3. Calculate statistics
    4. Detect anomalies (optional)

    Note: This test uses manual time range instead of DuckDB lookup
    since we're testing with fixture data.
    """
    # Use fixture-based extractor
    extractor_with_fixture = TimeSeriesDetailExtractor(base_path=fixture_base_path)

    metrics = ["heart_rate", "speed", "cadence"]

    # Manually specify time range (simulating split 1)
    start_time = 0
    end_time = 60

    # Extract metrics manually
    result = extractor_with_fixture.extract_metrics(
        dummy_activity_id, start_time, end_time, metrics
    )

    # Calculate statistics
    stats = extractor_with_fixture.calculate_statistics(result["time_series"], metrics)

    # Detect anomalies
    anomalies = extractor_with_fixture.detect_anomalies(
        result["time_series"], metrics, z_threshold=2.0
    )

    # Build response manually (simulating get_split_time_series_detail)
    response = {
        "activity_id": dummy_activity_id,
        "split_number": 1,
        "time_range": result["time_range"],
        "metrics": result["metrics"],
        "statistics": stats,
        "time_series": result["time_series"],
        "anomalies": anomalies,
    }

    # Check top-level structure
    assert "activity_id" in response
    assert "split_number" in response
    assert "time_range" in response
    assert "metrics" in response
    assert "statistics" in response
    assert "time_series" in response

    # Verify split number
    assert response["split_number"] == 1

    # Verify metrics
    assert set(response["metrics"]) == set(metrics)

    # Verify statistics are calculated
    for metric in metrics:
        assert metric in response["statistics"]
        assert "mean" in response["statistics"][metric]
        assert "std" in response["statistics"][metric]

    # Verify time series data exists
    assert len(response["time_series"]) > 0


@pytest.mark.unit
def test_handle_missing_activity_details(extractor: TimeSeriesDetailExtractor):
    """Test error handling when activity_details.json doesn't exist.

    Expected behavior:
    - Should return error message
    - Should not crash
    - Should indicate file not found
    """
    from unittest.mock import patch

    activity_id = 99999999999  # Non-existent activity

    # Mock _get_split_time_range to raise ValueError (simulating missing activity)
    with patch.object(
        extractor,
        "_get_split_time_range",
        side_effect=ValueError(
            f"Activity details not found for activity {activity_id}"
        ),
    ):
        result = extractor.get_split_time_series_detail(
            activity_id=activity_id, split_number=1
        )

    # Should have error field
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.unit
def test_handle_invalid_split_number(extractor: TimeSeriesDetailExtractor):
    """Test error handling for invalid split numbers.

    Expected behavior:
    - Should return error for split number 0 (1-based indexing)
    - Should return error for split number exceeding total splits
    - Should provide meaningful error messages
    """
    activity_id = 12345678901

    # Test split number 0
    result = extractor.get_split_time_series_detail(
        activity_id=activity_id, split_number=0
    )
    assert "error" in result
    assert "split" in result["error"].lower()

    # Test split number too large
    result = extractor.get_split_time_series_detail(
        activity_id=activity_id, split_number=999
    )
    assert "error" in result


@pytest.mark.unit
def test_metric_name_validation(extractor: TimeSeriesDetailExtractor):
    """Test validation of metric names.

    Expected behavior:
    - Should accept valid metric names from activity_details.json
    - Should reject invalid metric names with clear error
    - Should provide list of available metrics in error message
    """
    activity_id = 12345678901

    # Test with invalid metric name
    result = extractor.get_split_time_series_detail(
        activity_id=activity_id, split_number=1, metrics=["invalid_metric_name"]
    )

    # Should have error or warning about invalid metrics
    assert "error" in result or "invalid_metrics" in result
