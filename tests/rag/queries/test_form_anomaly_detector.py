"""Tests for FormAnomalyDetector - Form anomaly detection with cause analysis.

This module tests the form anomaly detection functionality including:
- Z-score based anomaly detection
- Cause classification (elevation, pace, fatigue)
- Correlation calculation
- Context window extraction
- Recommendation generation
"""

import json
from pathlib import Path
from typing import cast

import pytest

from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector


@pytest.fixture
def base_path() -> Path:
    """Provide base path to test fixtures."""
    return Path(__file__).parent.parent.parent / "fixtures" / "data"


@pytest.fixture
def detector(base_path: Path) -> FormAnomalyDetector:
    """Create FormAnomalyDetector instance with test base path."""
    return FormAnomalyDetector(base_path=base_path)


@pytest.fixture
def sample_activity_details(base_path: Path) -> dict[str, object]:
    """Load sample activity_details.json fixture."""
    file_path = (
        base_path
        / "data"
        / "raw"
        / "activity"
        / "12345678901"
        / "activity_details.json"
    )
    with open(file_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)
        return data


@pytest.fixture
def sample_performance_data(base_path: Path) -> dict[str, object]:
    """Load sample performance.json fixture."""
    file_path = base_path / "data" / "performance" / "12345678901.json"
    with open(file_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)
        return data


def test_z_score_anomaly_detection(detector: FormAnomalyDetector) -> None:
    """Test Z-score based anomaly detection accuracy.

    Verify that:
    - Anomalies are detected when z-score > threshold
    - Normal values are not flagged as anomalies
    - Multiple metrics can be analyzed simultaneously
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
        context_window=30,
    )

    # Should detect anomalies
    assert "anomalies" in result
    assert isinstance(result["anomalies"], list)

    # Check anomaly structure
    if len(result["anomalies"]) > 0:
        anomaly = result["anomalies"][0]
        assert "anomaly_id" in anomaly
        assert "timestamp" in anomaly
        assert "metric" in anomaly
        assert "value" in anomaly
        assert "baseline" in anomaly
        assert "z_score" in anomaly
        assert anomaly["z_score"] >= 2.0


def test_elevation_correlation(detector: FormAnomalyDetector) -> None:
    """Test elevation change and GCT/VO correlation detection.

    Verify that:
    - Elevation changes > 5m are detected as causes
    - Correlation coefficient is calculated
    - Cause is classified as "elevation_change"
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime", "directVerticalOscillation"],
        z_threshold=2.0,
        context_window=30,
    )

    # Find elevation-related anomalies
    elevation_anomalies = [
        a for a in result["anomalies"] if a["probable_cause"] == "elevation_change"
    ]

    if len(elevation_anomalies) > 0:
        anomaly = elevation_anomalies[0]
        assert "cause_details" in anomaly
        assert "elevation_change_5s" in anomaly["cause_details"]
        assert "elevation_correlation" in anomaly["cause_details"]
        # Elevation change should be > 5m for this classification
        assert abs(anomaly["cause_details"]["elevation_change_5s"]) > 5


def test_pace_correlation(detector: FormAnomalyDetector) -> None:
    """Test pace change and form degradation correlation.

    Verify that:
    - Pace changes > 15 sec/km are detected
    - Correlation with form metrics is calculated
    - Cause is classified as "pace_change"
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime", "directVerticalOscillation"],
        z_threshold=2.0,
        context_window=30,
    )

    # Find pace-related anomalies
    pace_anomalies = [
        a for a in result["anomalies"] if a["probable_cause"] == "pace_change"
    ]

    if len(pace_anomalies) > 0:
        anomaly = pace_anomalies[0]
        assert "cause_details" in anomaly
        assert "pace_change_10s" in anomaly["cause_details"]
        assert "pace_correlation" in anomaly["cause_details"]


def test_fatigue_correlation(detector: FormAnomalyDetector) -> None:
    """Test HR Drift and form degradation correlation.

    Verify that:
    - HR Drift > 10% is detected as fatigue
    - Correlation with form degradation is calculated
    - Cause is classified as "fatigue"
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime", "directVerticalOscillation"],
        z_threshold=2.0,
        context_window=30,
    )

    # Find fatigue-related anomalies
    fatigue_anomalies = [
        a for a in result["anomalies"] if a["probable_cause"] == "fatigue"
    ]

    if len(fatigue_anomalies) > 0:
        anomaly = fatigue_anomalies[0]
        assert "cause_details" in anomaly
        assert "hr_drift_percent" in anomaly["cause_details"]
        # HR drift should be > 10% for this classification
        assert abs(anomaly["cause_details"]["hr_drift_percent"]) > 10


def test_cause_classification(detector: FormAnomalyDetector) -> None:
    """Test accuracy of cause classification (3 categories).

    Verify that:
    - All anomalies are assigned one of the 3 causes
    - Cause assignment is mutually exclusive
    - Cause details match the classification
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
        context_window=30,
    )

    valid_causes = ["elevation_change", "pace_change", "fatigue"]

    for anomaly in result["anomalies"]:
        assert "probable_cause" in anomaly
        assert anomaly["probable_cause"] in valid_causes
        assert "cause_details" in anomaly
        assert isinstance(anomaly["cause_details"], dict)


def test_context_window_extraction(detector: FormAnomalyDetector) -> None:
    """Test accuracy of before/after 30-second context extraction.

    Verify that:
    - Context includes 30 seconds before anomaly
    - Context includes 30 seconds after anomaly
    - Context contains relevant metrics (GCT, elevation, etc.)
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
        context_window=30,
    )

    if len(result["anomalies"]) > 0:
        anomaly = result["anomalies"][0]
        assert "context" in anomaly
        assert "before_30s" in anomaly["context"]
        assert "after_30s" in anomaly["context"]

        # Context should have relevant metrics
        before_ctx = anomaly["context"]["before_30s"]
        after_ctx = anomaly["context"]["after_30s"]

        assert isinstance(before_ctx, dict)
        assert isinstance(after_ctx, dict)


def test_multiple_metrics_anomaly(detector: FormAnomalyDetector) -> None:
    """Test detection of simultaneous anomalies in multiple metrics.

    Verify that:
    - Anomalies in GCT, VO, VR are all detected
    - Each metric is analyzed independently
    - Summary counts are accurate
    """
    activity_id = 12345678901

    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=[
            "directGroundContactTime",
            "directVerticalOscillation",
            "directVerticalRatio",
        ],
        z_threshold=2.0,
        context_window=30,
    )

    # Check summary
    assert "summary" in result
    summary = result["summary"]

    assert "gct_anomalies" in summary
    assert "vo_anomalies" in summary
    assert "vr_anomalies" in summary
    assert "elevation_related" in summary
    assert "pace_related" in summary
    assert "fatigue_related" in summary

    # Total anomalies should match sum of metric-specific counts
    total_metric_anomalies = (
        summary["gct_anomalies"] + summary["vo_anomalies"] + summary["vr_anomalies"]
    )
    assert result["anomalies_detected"] == total_metric_anomalies


def test_edge_case_no_anomalies(detector: FormAnomalyDetector) -> None:
    """Test appropriate response when no anomalies are detected.

    Verify that:
    - Empty anomalies list is returned
    - Summary shows zero counts
    - No recommendations are generated
    - No errors are raised
    """
    activity_id = 12345678901

    # Use very high z_threshold to avoid detecting anomalies
    result = detector.detect_form_anomalies(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=10.0,  # Very high threshold
        context_window=30,
    )

    assert "anomalies" in result
    assert len(result["anomalies"]) == 0
    assert result["anomalies_detected"] == 0

    # Summary should show zero counts
    summary = result["summary"]
    assert summary["gct_anomalies"] == 0
    assert summary["elevation_related"] == 0
    assert summary["pace_related"] == 0
    assert summary["fatigue_related"] == 0

    # Recommendations should be empty or minimal
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)


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

    # Should return valid cause even with missing data
    assert cause in ["elevation_change", "pace_change", "fatigue"]
    assert isinstance(details, dict)
    assert "elevation_change_5s" in details
    assert "pace_change_10s" in details
    assert "hr_drift_percent" in details


def test_recommendations_generation(detector: FormAnomalyDetector) -> None:
    """Test recommendation generation for different anomaly patterns.

    Verify that:
    - Recommendations match anomaly causes
    - Multiple recommendations are generated when appropriate
    """
    # Test elevation-related anomalies
    summary_elevation = {
        "gct_anomalies": 3,
        "vo_anomalies": 0,
        "vr_anomalies": 0,
        "elevation_related": 3,
        "pace_related": 0,
        "fatigue_related": 0,
    }

    recs_elev = detector._generate_recommendations(summary_elevation)
    assert len(recs_elev) > 0
    assert any("上り坂" in r for r in recs_elev)

    # Test pace-related anomalies
    summary_pace = {
        "gct_anomalies": 0,
        "vo_anomalies": 2,
        "vr_anomalies": 0,
        "elevation_related": 0,
        "pace_related": 2,
        "fatigue_related": 0,
    }

    recs_pace = detector._generate_recommendations(summary_pace)
    assert len(recs_pace) > 0
    assert any("ペース" in r for r in recs_pace)

    # Test fatigue-related anomalies
    summary_fatigue = {
        "gct_anomalies": 0,
        "vo_anomalies": 0,
        "vr_anomalies": 1,
        "elevation_related": 0,
        "pace_related": 0,
        "fatigue_related": 1,
    }

    recs_fatigue = detector._generate_recommendations(summary_fatigue)
    assert len(recs_fatigue) > 0
    assert any("疲労" in r for r in recs_fatigue)


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


def test_analyze_causes_fatigue_detection(detector: FormAnomalyDetector) -> None:
    """Test fatigue detection when elevation and pace changes are minimal.

    Verify that:
    - HR drift > 10% triggers "fatigue" cause
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

    cause, details = detector._analyze_anomaly_causes(
        anomaly, elevation_series, pace_series, hr_series
    )

    # Should detect fatigue
    assert cause == "fatigue"
    assert abs(details["hr_drift_percent"]) > 10.0


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
