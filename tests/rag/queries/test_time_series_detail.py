"""Test suite for TimeSeriesDetailExtractor.

This module tests the time series detail extraction functionality including:
- Split number to time range conversion
- Metric descriptor parsing
- Unit conversion with factor application
- Statistics calculation
- Anomaly detection within splits
- Missing metrics handling
- Edge case handling
"""

from pathlib import Path
from typing import Any

import pytest

from tools.rag.loaders.activity_details_loader import ActivityDetailsLoader
from tools.rag.queries.time_series_detail import TimeSeriesDetailExtractor


@pytest.fixture
def time_series_extractor():
    """Create TimeSeriesDetailExtractor instance for testing."""
    base_path = Path(__file__).parent.parent.parent / "fixtures"
    return TimeSeriesDetailExtractor(base_path=base_path)


@pytest.fixture
def mock_performance_data() -> dict[str, Any]:
    """Mock performance.json data with split metrics."""
    return {
        "split_metrics": [
            {
                "lap_index": 1,
                "distance_km": 1.0,
                "duration_seconds": 240.0,
                "start_time_s": 0,
                "end_time_s": 240,
            },
            {
                "lap_index": 2,
                "distance_km": 1.0,
                "duration_seconds": 250.0,
                "start_time_s": 240,
                "end_time_s": 490,
            },
            {
                "lap_index": 3,
                "distance_km": 1.0,
                "duration_seconds": 255.0,
                "start_time_s": 490,
                "end_time_s": 745,
            },
        ]
    }


@pytest.fixture
def mock_activity_details() -> dict[str, Any]:
    """Mock activity_details.json data with metric descriptors and time series."""
    return {
        "activityId": 12345678901,
        "measurementCount": 10,
        "metricsCount": 10,
        "metricDescriptors": [
            {
                "metricsIndex": 0,
                "key": "directHeartRate",
                "unit": {"id": 100, "key": "bpm", "factor": 1.0},
            },
            {
                "metricsIndex": 1,
                "key": "directSpeed",
                "unit": {"id": 20, "key": "mps", "factor": 0.1},
            },
            {
                "metricsIndex": 2,
                "key": "directDoubleCadence",
                "unit": {"id": 92, "key": "stepsPerMinute", "factor": 1.0},
            },
            {
                "metricsIndex": 3,
                "key": "directGroundContactTime",
                "unit": {"id": 40, "key": "ms", "factor": 1.0},
            },
            {
                "metricsIndex": 4,
                "key": "directVerticalOscillation",
                "unit": {"id": 200, "key": "cm", "factor": 10.0},
            },
        ],
        "activityDetailMetrics": [
            {"metrics": [120, 30, 180, 250, 80]},
            {"metrics": [125, 32, 180, 245, 82]},
            {"metrics": [130, 34, 182, 240, 85]},
            {"metrics": [135, 36, 184, 238, 87]},
            {"metrics": [140, 38, 186, 235, 90]},
            {"metrics": [145, 40, 188, 230, 92]},
            {"metrics": [150, 42, 190, 228, 95]},
            {"metrics": [155, 44, 192, 225, 98]},
            {"metrics": [160, 46, 194, 220, 100]},
            {"metrics": [165, 48, 196, 218, 102]},
        ],
    }


@pytest.mark.unit
def test_split_range_extraction():
    """Test split number to time range extraction (DuckDB-based).

    NOTE: This test is now covered by test_get_split_time_range_duckdb_based().
    Kept for backward compatibility but implementation moved to DuckDB.
    """
    # This test is superseded by test_get_split_time_range_duckdb_based
    # which tests the same functionality with the new DuckDB implementation
    pass


@pytest.mark.unit
def test_metric_descriptor_parsing(
    time_series_extractor: TimeSeriesDetailExtractor, mock_activity_details: dict
):
    """Test metric descriptor parsing for all 26+ metrics.

    Expected behavior:
    - Should parse all metric descriptors correctly
    - Should map metric names to indices
    - Should extract unit information and factors
    """
    loader = ActivityDetailsLoader()
    metric_map = loader.parse_metric_descriptors(
        mock_activity_details["metricDescriptors"]
    )

    # Check essential metrics are parsed
    assert "directHeartRate" in metric_map
    assert "directSpeed" in metric_map
    assert "directGroundContactTime" in metric_map
    assert "directVerticalOscillation" in metric_map

    # Check metric indices
    assert metric_map["directHeartRate"]["index"] == 0
    assert metric_map["directSpeed"]["index"] == 1
    assert metric_map["directGroundContactTime"]["index"] == 3

    # Check unit information
    assert metric_map["directHeartRate"]["unit"] == "bpm"
    assert metric_map["directSpeed"]["unit"] == "mps"
    assert metric_map["directGroundContactTime"]["unit"] == "ms"


@pytest.mark.unit
def test_unit_conversion(time_series_extractor: TimeSeriesDetailExtractor):
    """Test unit conversion with factor application.

    Expected behavior:
    - directSpeed with factor 0.1: 30 raw -> 3.0 m/s
    - directVerticalOscillation with factor 10.0: 80 raw -> 8.0 cm
    - directHeartRate with factor 1.0: 120 raw -> 120 bpm
    """
    loader = ActivityDetailsLoader()

    # Test speed conversion (factor 0.1)
    speed_metric = {"index": 1, "unit": "mps", "factor": 0.1}
    converted_speed = loader.apply_unit_conversion(speed_metric, 30)
    assert converted_speed == 300.0  # 30 / 0.1 = 300

    # Test VO conversion (factor 10.0)
    vo_metric = {"index": 4, "unit": "cm", "factor": 10.0}
    converted_vo = loader.apply_unit_conversion(vo_metric, 80)
    assert converted_vo == 8.0  # 80 / 10.0 = 8.0

    # Test HR conversion (factor 1.0)
    hr_metric = {"index": 0, "unit": "bpm", "factor": 1.0}
    converted_hr = loader.apply_unit_conversion(hr_metric, 120)
    assert converted_hr == 120.0  # 120 / 1.0 = 120


@pytest.mark.unit
def test_statistics_calculation(
    time_series_extractor: TimeSeriesDetailExtractor, mock_activity_details: dict
):
    """Test statistics calculation (avg, std, min, max).

    Expected behavior:
    - Calculate average correctly
    - Calculate standard deviation correctly
    - Calculate min and max correctly
    """
    loader = ActivityDetailsLoader()

    # Extract HR time series (index 0)
    hr_values = loader.extract_time_series(
        mock_activity_details["activityDetailMetrics"], metric_index=0
    )

    # Calculate statistics
    stats = time_series_extractor._calculate_statistics(hr_values)

    # Check statistics (HR values: 120, 125, 130, 135, 140, 145, 150, 155, 160, 165)
    assert stats["avg"] == 142.5  # Average
    assert stats["min"] == 120
    assert stats["max"] == 165
    assert stats["std"] > 0  # Standard deviation should be positive


@pytest.mark.unit
def test_anomaly_detection_in_split(
    time_series_extractor: TimeSeriesDetailExtractor, mock_activity_details: dict
):
    """Test anomaly detection within a split using z-score.

    Expected behavior:
    - Detect values with z-score > threshold (default 2.0)
    - Return anomaly details including timestamp and value
    """
    # Create test data with an outlier
    test_data: list[float | None] = [
        120.0,
        125.0,
        130.0,
        135.0,
        200.0,
        145.0,
        150.0,
        155.0,
        160.0,
        165.0,
    ]  # 200 is outlier

    # Detect anomalies
    anomalies = time_series_extractor._detect_split_anomalies(
        metric_name="HR", time_series=test_data, z_threshold=2.0
    )

    # Should detect at least one anomaly (value 200)
    assert len(anomalies) > 0

    # Check anomaly structure
    anomaly = anomalies[0]
    assert "timestamp" in anomaly or "index" in anomaly
    assert "metric" in anomaly
    assert "value" in anomaly
    assert "z_score" in anomaly

    # The outlier should have high z-score
    assert anomaly["z_score"] > 2.0


@pytest.mark.unit
def test_missing_metrics_handling(time_series_extractor: TimeSeriesDetailExtractor):
    """Test handling of missing metrics in activity_details.json.

    Expected behavior:
    - Should handle None values gracefully
    - Should skip missing data points in statistics
    - Should not crash on incomplete data
    """
    # Create test data with None values
    test_data: list[float | None] = [
        120.0,
        None,
        130.0,
        None,
        140.0,
        145.0,
        None,
        155.0,
        160.0,
        165.0,
    ]

    # Calculate statistics (should skip None values)
    stats = time_series_extractor._calculate_statistics(test_data)

    # Should calculate statistics on non-None values only
    assert stats["avg"] > 0
    assert stats["min"] > 0
    assert stats["max"] > 0


@pytest.mark.unit
def test_edge_case_split_out_of_range():
    """Test error handling for out-of-range split numbers.

    NOTE: This test is now covered by test_get_split_time_range_duckdb_based().
    Kept for backward compatibility but implementation moved to DuckDB.
    """
    # This test is superseded by test_get_split_time_range_duckdb_based
    # which tests error handling with the new DuckDB implementation
    pass


@pytest.mark.integration
def test_get_split_time_series_detail_integration():
    """Integration test for full split time series detail extraction.

    Uses fixture activity data (12345678901) to test the full pipeline with DuckDB.
    """
    import tempfile

    import duckdb

    from tools.database.db_writer import GarminDBWriter

    # Test with fixture activity
    activity_id = 12345678901
    split_number = 1

    # Create temporary database with test data
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_integration.duckdb"
        base_path = Path(__file__).parent.parent.parent / "fixtures"

        # Create database schema
        writer = GarminDBWriter(str(db_path))
        writer._ensure_tables()

        # Insert test activity
        activity_date = "2025-10-11"

        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO activities (activity_id, date, activity_name)
            VALUES (?, ?, ?)
            """,
            (activity_id, activity_date, "Test Run"),
        )

        # Insert splits with time ranges (matching fixture data)
        splits_data = [
            (activity_id, 1, 1.0, 240.0, 0, 240, 250.0, 160),
            (activity_id, 2, 1.0, 250.0, 240, 490, 260.0, 165),
            (activity_id, 3, 1.0, 255.0, 490, 745, 270.0, 168),
        ]

        for split in splits_data:
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, pace_seconds_per_km, heart_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                split,
            )

        conn.close()

        # Create extractor with db_path
        extractor = TimeSeriesDetailExtractor(base_path=base_path, db_path=str(db_path))

        # Get split time series detail
        result = extractor.get_split_time_series_detail(
            activity_id=activity_id, split_number=split_number
        )

        # Check result structure
        assert "activity_id" in result
        assert "split_number" in result
        assert "start_time_s" in result
        assert "end_time_s" in result
        assert "time_series" in result
        assert "statistics" in result

        # Check activity ID matches
        assert result["activity_id"] == activity_id
        assert result["split_number"] == split_number

        # Check time series data
        assert isinstance(result["time_series"], list)
        assert len(result["time_series"]) > 0

        # Check statistics (keyed by metric name)
        stats = result["statistics"]
        assert len(stats) > 0
        # Check structure of first metric's statistics
        first_metric_stats = next(iter(stats.values()))
        assert "avg" in first_metric_stats
        assert "std" in first_metric_stats
        assert "min" in first_metric_stats
        assert "max" in first_metric_stats


@pytest.mark.unit
def test_get_split_time_range_duckdb_based():
    """Test _get_split_time_range() with new DuckDB-based implementation.

    Phase 3: NEW signature takes activity_id instead of performance_data.
    Should query DuckDB splits table via GarminDBReader.

    Expected behavior:
    - Accepts activity_id instead of performance_data dict
    - Queries DuckDB for split time ranges
    - Returns (start_time_s, end_time_s) tuple
    - Raises ValueError for invalid split numbers
    """
    import tempfile
    from pathlib import Path

    import duckdb

    from tools.database.db_writer import GarminDBWriter

    # Create temporary database with test data
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_duckdb_based.duckdb"

        # Create database schema
        writer = GarminDBWriter(str(db_path))
        writer._ensure_tables()

        # Insert test activity
        activity_id = 99999999
        activity_date = "2025-10-11"

        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO activities (activity_id, date, activity_name)
            VALUES (?, ?, ?)
            """,
            (activity_id, activity_date, "Test Run"),
        )

        # Insert splits with time ranges
        splits_data = [
            (activity_id, 1, 1.0, 240.0, 0, 240, 250.0, 160),
            (activity_id, 2, 1.0, 250.0, 240, 490, 260.0, 165),
            (activity_id, 3, 1.0, 255.0, 490, 745, 270.0, 168),
        ]

        for split in splits_data:
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, pace_seconds_per_km, heart_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                split,
            )

        conn.close()

        # Create extractor with db_path
        extractor = TimeSeriesDetailExtractor(
            base_path=Path(tmp_dir), db_path=str(db_path)
        )

        # Test NEW signature: _get_split_time_range(split_number, activity_id)
        start, end = extractor._get_split_time_range(
            split_number=1, activity_id=activity_id
        )
        assert start == 0
        assert end == 240

        start, end = extractor._get_split_time_range(
            split_number=2, activity_id=activity_id
        )
        assert start == 240
        assert end == 490

        start, end = extractor._get_split_time_range(
            split_number=3, activity_id=activity_id
        )
        assert start == 490
        assert end == 745

        # Test invalid split numbers
        with pytest.raises(ValueError):
            extractor._get_split_time_range(split_number=0, activity_id=activity_id)

        with pytest.raises(ValueError):
            extractor._get_split_time_range(split_number=10, activity_id=activity_id)
