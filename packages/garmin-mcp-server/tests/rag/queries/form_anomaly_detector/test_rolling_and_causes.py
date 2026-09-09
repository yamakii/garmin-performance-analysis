"""FormAnomalyDetector: rolling statistics, context extraction and cause analysis."""

from typing import cast

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


@pytest.mark.unit
def test_rolling_stats_calculation(detector: FormAnomalyDetector) -> None:
    """Test rolling statistics calculation with various window sizes.

    Verify that:
    - Rolling mean and std are calculated correctly
    - Window boundaries are handled properly
    - None values are filtered out
    """
    # Test with simple time series
    time_series = [1.0, 2.0, 3.0, 4.0, 5.0, None, 6.0, 7.0, 8.0, 9.0]
    rolling_means, rolling_stds = detector._calculate_rolling_stats(
        time_series, window_size=4
    )

    # Should have same length as input
    assert len(rolling_means) == len(time_series)
    assert len(rolling_stds) == len(time_series)

    # All values should be non-negative
    assert all(m >= 0 for m in rolling_means)
    assert all(s >= 0 for s in rolling_stds)


@pytest.mark.unit
def test_detect_anomalies_with_zero_std(detector: FormAnomalyDetector) -> None:
    """Test anomaly detection when standard deviation is zero.

    Verify that:
    - No anomalies are detected when std is 0
    - No division by zero errors occur
    """
    # Create time series with constant values (std = 0)
    time_series: list[float | None] = [5.0] * 10
    rolling_means = [5.0] * 10
    rolling_stds = [0.0] * 10

    anomalies = detector._detect_anomalies_by_zscore(
        "testMetric", time_series, rolling_means, rolling_stds, z_threshold=2.0
    )

    # Should not detect any anomalies (std = 0 → skip)
    assert len(anomalies) == 0


@pytest.mark.unit
def test_context_extraction_edge_cases(detector: FormAnomalyDetector) -> None:
    """Test context window extraction at boundaries.

    Verify that:
    - Context at start of activity (timestamp = 0) works
    - Context at end of activity works
    - Context with insufficient data is handled
    """
    metric_series: list[float | None] = [1.0, 2.0, 3.0, 4.0, 5.0]
    elevation_series: list[float | None] = [10.0, 11.0, 12.0, 13.0, 14.0]

    # Test at start (timestamp = 0)
    context_start = detector._extract_context(
        timestamp=0,
        metric_series=metric_series,
        elevation_series=elevation_series,
        window=2,
    )

    assert "before_30s" in context_start
    assert "after_30s" in context_start

    # Test at end (timestamp = 4)
    context_end = detector._extract_context(
        timestamp=4,
        metric_series=metric_series,
        elevation_series=elevation_series,
        window=2,
    )

    assert "before_30s" in context_end
    assert "after_30s" in context_end


@pytest.mark.unit
def test_analyze_anomaly_causes_with_missing_metrics(
    detector: FormAnomalyDetector,
) -> None:
    """Test cause analysis when contextual metrics are missing.

    Verify that:
    - Handles empty or sparse time series gracefully
    - Returns valid cause classification even with missing data
    """
    anomaly = {"timestamp": 50, "metric": "directGroundContactTime", "value": 230.0}

    # Sparse elevation series (mostly None)
    elevation_series: list[float | None] = cast(
        list[float | None], [None] * 40 + [10.0, 11.0, 12.0] + [None] * 60
    )
    pace_series: list[float | None] = cast(list[float | None], [None] * 100)
    hr_series: list[float | None] = cast(
        list[float | None], [150.0] * 50 + [160.0] * 50
    )

    cause, details = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series
    )

    # Should return valid cause even with missing data. With sparse context and
    # no sustained trend the anomaly falls through to "isolated" (#666).
    assert cause in ["elevation_change", "pace_change", "fatigue", "isolated"]
    assert isinstance(details, dict)
    assert "elevation_change_5s" in details
    assert "pace_change_10s" in details
    assert "hr_drift_percent" in details


@pytest.mark.unit
def test_recommendations_generation(detector: FormAnomalyDetector) -> None:
    """Test recommendation generation for different anomaly patterns.

    Verify that (new anomaly-list signature, #666):
    - Recommendations match anomaly causes
    - Multiple recommendations are generated when appropriate
    """
    # Test elevation-related anomalies (GCT dominant)
    recs_elev = detector._generate_recommendations(
        [
            {
                "probable_cause": "elevation_change",
                "metric": "directGroundContactTime",
            },
            {
                "probable_cause": "elevation_change",
                "metric": "directGroundContactTime",
            },
        ]
    )
    assert len(recs_elev) > 0
    assert any("上り坂" in r for r in recs_elev)

    # Test pace-related anomalies (VO dominant)
    recs_pace = detector._generate_recommendations(
        [
            {
                "probable_cause": "pace_change",
                "metric": "directVerticalOscillation",
            },
            {
                "probable_cause": "pace_change",
                "metric": "directVerticalOscillation",
            },
        ]
    )
    assert len(recs_pace) > 0
    assert any("ペース" in r for r in recs_pace)

    # Test fatigue-related anomalies (VR dominant)
    recs_fatigue = detector._generate_recommendations(
        [
            {"probable_cause": "fatigue", "metric": "directVerticalRatio"},
        ]
    )
    assert len(recs_fatigue) > 0
    assert any("疲労" in r for r in recs_fatigue)


@pytest.mark.unit
def test_rolling_stats_with_insufficient_data(detector: FormAnomalyDetector) -> None:
    """Test rolling statistics with insufficient data points.

    Verify that:
    - Returns zeros when window has < 2 valid values
    - Handles single data point gracefully
    """
    # Single value time series
    time_series_single: list[float | None] = [5.0]
    means, stds = detector._calculate_rolling_stats(time_series_single, window_size=4)

    assert len(means) == 1
    assert len(stds) == 1
    # Should return 0 for both (< 2 values)
    assert means[0] == 0.0
    assert stds[0] == 0.0


@pytest.mark.unit
def test_detect_anomalies_with_none_values(detector: FormAnomalyDetector) -> None:
    """Test anomaly detection skips None values correctly.

    Verify that:
    - None values in time series are skipped
    - Anomaly detection continues for valid values
    """
    time_series = [1.0, 2.0, None, 4.0, 5.0, None, 7.0, 20.0, 9.0, 10.0]
    rolling_means = [5.0] * 10
    rolling_stds = [2.0] * 10

    anomalies = detector._detect_anomalies_by_zscore(
        "testMetric", time_series, rolling_means, rolling_stds, z_threshold=2.0
    )

    # Should detect the outlier at index 7 (value=20.0)
    # Z-score = |20 - 5| / 2 = 7.5 > 2.0
    assert len(anomalies) > 0
    assert any(a["value"] == 20.0 for a in anomalies)


@pytest.mark.unit
def test_analyze_causes_elevation_priority(detector: FormAnomalyDetector) -> None:
    """Test that elevation change has priority in cause classification.

    Verify that:
    - Elevation change > 5m triggers "elevation_change" cause
    - Even when pace and HR drift are also present
    """
    anomaly = {"timestamp": 50, "metric": "directGroundContactTime", "value": 230.0}

    # Create elevation change > 5m
    elevation_series: list[float | None] = cast(
        list[float | None],
        [10.0] * 45 + [10.0, 11.0, 12.0, 13.0, 14.0, 16.0, 18.0, 20.0] + [20.0] * 50,
    )

    # Also have pace change
    pace_series: list[float | None] = cast(
        list[float | None],
        [4.0] * 45 + [4.0, 4.2, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0] + [7.0] * 50,
    )

    # Also have HR drift
    hr_series: list[float | None] = cast(
        list[float | None], [150.0] * 50 + [170.0] * 50
    )

    cause, details = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series
    )

    # Should prioritize elevation change
    assert cause == "elevation_change"
    assert details["elevation_change_5s"] > 5.0


@pytest.mark.unit
def test_analyze_causes_pace_priority(detector: FormAnomalyDetector) -> None:
    """Test that pace change has priority over fatigue.

    Verify that:
    - Pace change > 0.25 min/km triggers "pace_change" cause
    - When elevation change is small but pace change is significant
    """
    anomaly = {"timestamp": 50, "metric": "directGroundContactTime", "value": 230.0}

    # Small elevation change
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)

    # Significant pace change
    pace_series: list[float | None] = cast(
        list[float | None],
        [4.0] * 45 + [4.0, 4.2, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0] + [7.0] * 50,
    )

    # Also have HR drift
    hr_series: list[float | None] = cast(
        list[float | None], [150.0] * 50 + [170.0] * 50
    )

    cause, details = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series
    )

    # Should prioritize pace change
    assert cause == "pace_change"
    assert details["pace_change_10s"] > 0.25


@pytest.mark.unit
def test_analyze_causes_default_isolated(detector: FormAnomalyDetector) -> None:
    """Test isolated spikes (no elev/pace/fatigue signal) -> "isolated" (#666).

    Verify that:
    - An anomaly with small elevation change, small pace change, and no
      sustained degradation is classified as "isolated"
    - No fabricated pace_correlation is added to the details
    """
    anomaly = {"timestamp": 50, "metric": "directGroundContactTime", "value": 230.0}

    # Flat elevation, flat pace, flat HR -> no identifiable cause.
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)
    pace_series: list[float | None] = cast(list[float | None], [4.0] * 100)
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    cause, details = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series, sustained_degradation=False
    )

    assert cause == "isolated"
    assert "pace_correlation" not in details


@pytest.mark.unit
def test_analyze_causes_fatigue_detection(detector: FormAnomalyDetector) -> None:
    """Test fatigue detection when elevation and pace changes are minimal.

    Verify that:
    - HR drift > 10% AND a sustained degradation trend trigger "fatigue" cause
    - When elevation and pace changes are below thresholds
    """
    anomaly = {"timestamp": 500, "metric": "directGroundContactTime", "value": 230.0}

    # Minimal elevation change
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 600)

    # Very minimal pace change (< 0.25 min/km)
    # Small variation but below threshold
    pace_series: list[float | None] = cast(
        list[float | None], [4.0] * 450 + [4.05] * 50 + [4.1] * 100
    )

    # Significant HR drift (>10%)
    # Baseline (first 5 minutes = 300 seconds): 150 bpm average
    # Current (around timestamp 440-500): 172 bpm average
    # Drift: (172-150)/150 * 100 = 14.67%
    hr_series: list[float | None] = cast(
        list[float | None],
        [150.0] * 300 + [158.0] * 100 + [168.0] * 100 + [172.0] * 100,
    )

    # Issue #232: fatigue now requires a sustained degradation trend in addition
    # to HR drift.
    cause, details = detector._analyze_anomaly_causes(
        anomaly,
        elevation_series,
        pace_series,
        hr_series,
        sustained_degradation=True,
    )

    # Should detect fatigue
    assert cause == "fatigue"
    assert abs(details["hr_drift_percent"]) > 10.0


@pytest.mark.unit
def test_context_extraction_with_none_values(detector: FormAnomalyDetector) -> None:
    """Test context extraction filters None values correctly.

    Verify that:
    - None values are filtered before calculating statistics
    - Context calculation doesn't fail with sparse data
    """
    metric_series = [1.0, None, 3.0, None, 5.0, None, 7.0, None, 9.0, None]
    elevation_series = [10.0, None, 12.0, None, 14.0, None, 16.0, None, 18.0, None]

    context = detector._extract_context(
        timestamp=5,
        metric_series=metric_series,
        elevation_series=elevation_series,
        window=3,
    )

    # Should successfully calculate context even with None values
    assert "before_30s" in context
    assert "after_30s" in context
    assert context["before_30s"]["metric_avg"] > 0
    assert context["after_30s"]["metric_avg"] > 0
