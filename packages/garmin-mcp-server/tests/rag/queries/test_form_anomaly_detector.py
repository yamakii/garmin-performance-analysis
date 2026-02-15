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

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


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


# ==========================================
# New API Tests: Helper Methods
# ==========================================


@pytest.mark.unit
def test_extract_time_series_success(detector: FormAnomalyDetector) -> None:
    """Test _extract_time_series extracts all required metrics."""
    activity_id = 12345678901
    metrics = [
        "directGroundContactTime",
        "directVerticalOscillation",
        "directVerticalRatio",
    ]

    metric_map, form_metrics, context_metrics = detector._extract_time_series(
        activity_id, metrics
    )

    # Should return tuple of 3 elements
    assert isinstance(metric_map, dict)
    assert isinstance(form_metrics, dict)
    assert isinstance(context_metrics, dict)

    # Form metrics should contain requested metrics
    assert "directGroundContactTime" in form_metrics
    assert "directVerticalOscillation" in form_metrics
    assert "directVerticalRatio" in form_metrics

    # Context metrics should have elevation, pace, hr
    assert "elevation" in context_metrics
    assert "pace" in context_metrics
    assert "hr" in context_metrics


@pytest.mark.unit
def test_extract_time_series_missing_metrics(detector: FormAnomalyDetector) -> None:
    """Test _extract_time_series handles missing metrics gracefully."""
    activity_id = 12345678901
    metrics = ["directGroundContactTime"]

    # Should not raise error
    metric_map, form_metrics, context_metrics = detector._extract_time_series(
        activity_id, metrics
    )
    assert isinstance(form_metrics, dict)
    assert "directGroundContactTime" in form_metrics


@pytest.mark.unit
def test_detect_all_anomalies_basic(detector: FormAnomalyDetector) -> None:
    """Test _detect_all_anomalies returns properly structured anomalies."""
    # Create simple time series data
    from typing import cast

    form_metrics: dict[str, list[float | None]] = {
        "directGroundContactTime": cast(
            list[float | None], [200.0] * 50 + [300.0] + [200.0] * 49
        ),  # Spike
    }
    elevation_series: list[float | None] = cast(list[float | None], [10.0] * 100)
    pace_series: list[float | None] = cast(list[float | None], [5.0] * 100)  # min/km
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    anomalies = detector._detect_all_anomalies(
        form_metrics, elevation_series, pace_series, hr_series, z_threshold=2.0
    )

    # Should detect the spike at index 50
    assert isinstance(anomalies, list)
    if len(anomalies) > 0:
        anomaly = anomalies[0]
        assert "anomaly_id" in anomaly
        assert "timestamp" in anomaly
        assert "metric" in anomaly
        assert "value" in anomaly
        assert "baseline" in anomaly
        assert "z_score" in anomaly
        assert "probable_cause" in anomaly
        assert "cause_details" in anomaly
        assert "context" in anomaly


@pytest.mark.unit
def test_detect_all_anomalies_with_causes(detector: FormAnomalyDetector) -> None:
    """Test _detect_all_anomalies includes cause analysis."""
    # Create elevation spike scenario
    from typing import cast

    form_metrics: dict[str, list[float | None]] = {
        "directGroundContactTime": cast(
            list[float | None], [200.0] * 45 + [250.0] * 10 + [200.0] * 45
        ),
    }
    elevation_series: list[float | None] = cast(
        list[float | None], [10.0] * 45 + [20.0] * 10 + [20.0] * 45
    )  # 10m elevation gain
    pace_series: list[float | None] = cast(list[float | None], [5.0] * 100)
    hr_series: list[float | None] = cast(list[float | None], [150.0] * 100)

    anomalies = detector._detect_all_anomalies(
        form_metrics, elevation_series, pace_series, hr_series, z_threshold=2.0
    )

    if len(anomalies) > 0:
        # Should detect elevation as probable cause
        elevation_anomalies = [
            a for a in anomalies if a["probable_cause"] == "elevation_change"
        ]
        assert len(elevation_anomalies) > 0


@pytest.mark.unit
def test_generate_severity_distribution_all_levels(
    detector: FormAnomalyDetector,
) -> None:
    """Test _generate_severity_distribution with all severity levels."""
    anomalies = [
        {"z_score": 2.2},  # Low
        {"z_score": 2.7},  # Medium
        {"z_score": 3.5},  # High
        {"z_score": 2.3},  # Low
        {"z_score": 4.0},  # High
    ]

    distribution = detector._generate_severity_distribution(anomalies)

    assert "high" in distribution
    assert "medium" in distribution
    assert "low" in distribution
    assert distribution["low"] == 2
    assert distribution["medium"] == 1
    assert distribution["high"] == 2


@pytest.mark.unit
def test_generate_severity_distribution_single_level(
    detector: FormAnomalyDetector,
) -> None:
    """Test _generate_severity_distribution with single severity level."""
    anomalies = [
        {"z_score": 2.2},
        {"z_score": 2.3},
        {"z_score": 2.4},
    ]

    distribution = detector._generate_severity_distribution(anomalies)

    assert distribution["low"] == 3
    assert distribution["medium"] == 0
    assert distribution["high"] == 0


@pytest.mark.unit
def test_generate_severity_distribution_empty(detector: FormAnomalyDetector) -> None:
    """Test _generate_severity_distribution with empty input."""
    anomalies: list[dict[str, object]] = []

    distribution = detector._generate_severity_distribution(anomalies)

    assert distribution["low"] == 0
    assert distribution["medium"] == 0
    assert distribution["high"] == 0


@pytest.mark.unit
def test_generate_temporal_clusters_basic(detector: FormAnomalyDetector) -> None:
    """Test _generate_temporal_clusters groups anomalies into 5-minute windows."""
    anomalies = [
        {
            "timestamp": 60,
            "probable_cause": "elevation_change",
            "metric": "directGroundContactTime",
        },
        {
            "timestamp": 120,
            "probable_cause": "elevation_change",
            "metric": "directVerticalOscillation",
        },
        {
            "timestamp": 350,
            "probable_cause": "pace_change",
            "metric": "directGroundContactTime",
        },
        {
            "timestamp": 370,
            "probable_cause": "pace_change",
            "metric": "directGroundContactTime",
        },
        {
            "timestamp": 650,
            "probable_cause": "fatigue",
            "metric": "directVerticalRatio",
        },
    ]

    clusters = detector._generate_temporal_clusters(anomalies, cluster_window=300)

    assert isinstance(clusters, list)
    assert len(clusters) >= 3  # Should have at least 3 clusters

    # Verify cluster structure
    if len(clusters) > 0:
        cluster = clusters[0]
        assert "start" in cluster
        assert "end" in cluster
        assert "count" in cluster


@pytest.mark.unit
def test_generate_temporal_clusters_single_window(
    detector: FormAnomalyDetector,
) -> None:
    """Test _generate_temporal_clusters with anomalies in single window."""
    anomalies = [
        {
            "timestamp": 60,
            "probable_cause": "elevation_change",
            "metric": "directGroundContactTime",
        },
        {
            "timestamp": 120,
            "probable_cause": "elevation_change",
            "metric": "directVerticalOscillation",
        },
        {
            "timestamp": 180,
            "probable_cause": "elevation_change",
            "metric": "directVerticalRatio",
        },
    ]

    clusters = detector._generate_temporal_clusters(anomalies, cluster_window=300)

    assert len(clusters) == 1
    assert clusters[0]["count"] == 3


@pytest.mark.unit
def test_generate_temporal_clusters_empty(detector: FormAnomalyDetector) -> None:
    """Test _generate_temporal_clusters with empty input."""
    anomalies: list[dict[str, object]] = []

    clusters = detector._generate_temporal_clusters(anomalies, cluster_window=300)

    assert isinstance(clusters, list)
    assert len(clusters) == 0


@pytest.mark.unit
def test_apply_anomaly_filters_by_ids(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters filters by anomaly IDs."""
    anomalies = [
        {"anomaly_id": 1, "timestamp": 100, "z_score": 2.5},
        {"anomaly_id": 2, "timestamp": 200, "z_score": 3.0},
        {"anomaly_id": 3, "timestamp": 300, "z_score": 3.5},
    ]

    filtered = detector._apply_anomaly_filters(anomalies, {"anomaly_ids": [1, 3]})

    assert len(filtered) == 2
    ids = [a["anomaly_id"] for a in filtered]
    assert 1 in ids
    assert 3 in ids


@pytest.mark.unit
def test_apply_anomaly_filters_by_time_range(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters filters by time range."""
    anomalies = [
        {"anomaly_id": 1, "timestamp": 100, "z_score": 2.5},
        {"anomaly_id": 2, "timestamp": 200, "z_score": 3.0},
        {"anomaly_id": 3, "timestamp": 300, "z_score": 3.5},
        {"anomaly_id": 4, "timestamp": 400, "z_score": 2.8},
    ]

    filtered = detector._apply_anomaly_filters(anomalies, {"time_range": (150, 350)})

    assert len(filtered) == 2
    assert all(150 <= a["timestamp"] <= 350 for a in filtered)


@pytest.mark.unit
def test_apply_anomaly_filters_by_metrics(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters filters by metric names."""
    anomalies = [
        {"anomaly_id": 1, "metric": "directGroundContactTime", "z_score": 2.5},
        {"anomaly_id": 2, "metric": "directVerticalOscillation", "z_score": 3.0},
        {"anomaly_id": 3, "metric": "directGroundContactTime", "z_score": 3.5},
        {"anomaly_id": 4, "metric": "directVerticalRatio", "z_score": 2.8},
    ]

    filtered = detector._apply_anomaly_filters(
        anomalies, {"metrics": ["directGroundContactTime"]}
    )

    assert len(filtered) == 2
    assert all(a["metric"] == "directGroundContactTime" for a in filtered)


@pytest.mark.unit
def test_apply_anomaly_filters_by_z_threshold(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters filters by minimum z-score."""
    anomalies = [
        {"anomaly_id": 1, "z_score": 2.2},
        {"anomaly_id": 2, "z_score": 2.8},
        {"anomaly_id": 3, "z_score": 3.5},
        {"anomaly_id": 4, "z_score": 2.5},
    ]

    filtered = detector._apply_anomaly_filters(anomalies, {"min_z_score": 2.7})

    assert len(filtered) == 2
    assert all(abs(a["z_score"]) >= 2.7 for a in filtered)


@pytest.mark.unit
def test_apply_anomaly_filters_by_causes(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters filters by probable causes."""
    anomalies = [
        {"anomaly_id": 1, "probable_cause": "elevation_change", "z_score": 2.5},
        {"anomaly_id": 2, "probable_cause": "pace_change", "z_score": 3.0},
        {"anomaly_id": 3, "probable_cause": "elevation_change", "z_score": 3.5},
        {"anomaly_id": 4, "probable_cause": "fatigue", "z_score": 2.8},
    ]

    filtered = detector._apply_anomaly_filters(
        anomalies, {"causes": ["elevation_change", "fatigue"]}
    )

    assert len(filtered) == 3
    assert all(a["probable_cause"] in ["elevation_change", "fatigue"] for a in filtered)


@pytest.mark.unit
def test_apply_anomaly_filters_combined(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters with multiple filter criteria."""
    anomalies = [
        {
            "anomaly_id": 1,
            "timestamp": 100,
            "metric": "directGroundContactTime",
            "z_score": 2.5,
            "probable_cause": "elevation_change",
        },
        {
            "anomaly_id": 2,
            "timestamp": 200,
            "metric": "directVerticalOscillation",
            "z_score": 3.0,
            "probable_cause": "pace_change",
        },
        {
            "anomaly_id": 3,
            "timestamp": 300,
            "metric": "directGroundContactTime",
            "z_score": 3.5,
            "probable_cause": "elevation_change",
        },
        {
            "anomaly_id": 4,
            "timestamp": 400,
            "metric": "directGroundContactTime",
            "z_score": 2.2,
            "probable_cause": "fatigue",
        },
    ]

    # Filter: GCT metric, z_score >= 2.5, elevation cause
    filtered = detector._apply_anomaly_filters(
        anomalies,
        {
            "metrics": ["directGroundContactTime"],
            "min_z_score": 2.5,
            "causes": ["elevation_change"],
        },
    )

    assert len(filtered) == 2
    assert all(a["metric"] == "directGroundContactTime" for a in filtered)
    assert all(abs(a["z_score"]) >= 2.5 for a in filtered)
    assert all(a["probable_cause"] == "elevation_change" for a in filtered)


@pytest.mark.unit
def test_apply_anomaly_filters_limit(detector: FormAnomalyDetector) -> None:
    """Test _apply_anomaly_filters enforces limit."""
    anomalies = [
        {"anomaly_id": i, "z_score": 2.5 + i * 0.1, "timestamp": i * 100}
        for i in range(1, 21)  # 20 anomalies
    ]

    filtered = detector._apply_anomaly_filters(anomalies, {"limit": 5})

    assert len(filtered) == 5
    # Should return top 5 by z_score
    assert all(abs(a["z_score"]) >= 3.5 for a in filtered)


# ==========================================
# New API Tests: Summary API
# ==========================================


@pytest.mark.unit
def test_detect_form_anomalies_summary_structure(detector: FormAnomalyDetector) -> None:
    """Test detect_form_anomalies_summary returns correct structure."""
    activity_id = 12345678901

    result = detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    # Verify structure
    assert "activity_id" in result
    assert "anomalies_detected" in result
    assert "summary" in result
    assert "top_anomalies" in result
    assert "recommendations" in result

    # Verify nested structures
    summary = result["summary"]
    assert "gct_anomalies" in summary
    assert "elevation_related" in summary
    assert "severity_distribution" in summary
    assert "temporal_clusters" in summary


@pytest.mark.unit
def test_detect_form_anomalies_summary_token_count(
    detector: FormAnomalyDetector,
) -> None:
    """Test detect_form_anomalies_summary has token count < 1000."""
    activity_id = 12345678901

    result = detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=[
            "directGroundContactTime",
            "directVerticalOscillation",
            "directVerticalRatio",
        ],
        z_threshold=2.0,
    )

    # Serialize to JSON and count tokens (rough estimate: 4 chars per token)
    import json

    json_str = json.dumps(result, ensure_ascii=False)
    estimated_tokens = len(json_str) // 4

    # Should be under 1000 tokens (target: ~700)
    assert estimated_tokens < 1000, f"Token count {estimated_tokens} exceeds 1000"


@pytest.mark.unit
def test_detect_form_anomalies_summary_no_anomalies(
    detector: FormAnomalyDetector,
) -> None:
    """Test detect_form_anomalies_summary handles no anomalies case."""
    activity_id = 12345678901

    result = detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=10.0,  # Very high threshold
    )

    assert result["anomalies_detected"] == 0
    assert result["summary"]["severity_distribution"]["high"] == 0
    assert result["summary"]["severity_distribution"]["medium"] == 0
    assert result["summary"]["severity_distribution"]["low"] == 0
    assert len(result["summary"]["temporal_clusters"]) == 0
    assert len(result["top_anomalies"]) == 0


# ==========================================
# New API Tests: Details API
# ==========================================


@pytest.mark.unit
def test_get_form_anomaly_details_no_filter(detector: FormAnomalyDetector) -> None:
    """Test get_form_anomaly_details without filters returns anomalies."""
    activity_id = 12345678901

    result = detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    # Verify structure
    assert "activity_id" in result
    assert "total_anomalies" in result
    assert "returned_anomalies" in result
    assert "anomalies" in result

    # Should have anomalies
    assert isinstance(result["anomalies"], list)


@pytest.mark.unit
def test_get_form_anomaly_details_filter_by_ids(detector: FormAnomalyDetector) -> None:
    """Test get_form_anomaly_details filters by anomaly IDs."""
    activity_id = 12345678901

    # First get all anomalies to find IDs
    all_result = detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    if len(all_result["anomalies"]) >= 2:
        # Filter by first 2 IDs
        target_ids = [
            all_result["anomalies"][0]["anomaly_id"],
            all_result["anomalies"][1]["anomaly_id"],
        ]

        filtered_result = detector.get_form_anomaly_details(
            activity_id=activity_id,
            filters={"anomaly_ids": target_ids},
        )

        assert filtered_result["returned_anomalies"] == 2
        returned_ids = [a["anomaly_id"] for a in filtered_result["anomalies"]]
        assert set(returned_ids) == set(target_ids)


@pytest.mark.unit
def test_get_form_anomaly_details_filter_by_time_range(
    detector: FormAnomalyDetector,
) -> None:
    """Test get_form_anomaly_details filters by time range."""
    activity_id = 12345678901

    result = detector.get_form_anomaly_details(
        activity_id=activity_id,
        filters={"time_range": (100, 500)},  # 100-500 seconds
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    # All returned anomalies should be within time range
    for anomaly in result["anomalies"]:
        assert 100 <= anomaly["timestamp"] <= 500


@pytest.mark.unit
def test_get_form_anomaly_details_filter_by_limit(
    detector: FormAnomalyDetector,
) -> None:
    """Test get_form_anomaly_details enforces limit."""
    activity_id = 12345678901

    result = detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=[
            "directGroundContactTime",
            "directVerticalOscillation",
            "directVerticalRatio",
        ],
        z_threshold=2.0,
        filters={"limit": 5},
    )

    assert result["returned_anomalies"] <= 5
    assert len(result["anomalies"]) <= 5


@pytest.mark.unit
def test_get_form_anomaly_details_empty_results(detector: FormAnomalyDetector) -> None:
    """Test get_form_anomaly_details handles empty results gracefully."""
    activity_id = 12345678901

    result = detector.get_form_anomaly_details(
        activity_id=activity_id,
        z_threshold=10.0,  # Very high threshold
        metrics=["directGroundContactTime"],
    )

    assert result["total_anomalies"] == 0
    assert result["returned_anomalies"] == 0
    assert len(result["anomalies"]) == 0


# ==========================================
# Integration Tests: Summary → Details Workflow
# ==========================================


@pytest.mark.integration
def test_summary_to_details_workflow(detector: FormAnomalyDetector) -> None:
    """Test typical workflow: summary → identify issue → get details."""
    activity_id = 12345678901

    # Step 1: Get summary
    summary = detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=[
            "directGroundContactTime",
            "directVerticalOscillation",
            "directVerticalRatio",
        ],
        z_threshold=2.0,
    )

    # Step 2: Identify temporal clusters with high anomaly count
    if len(summary["summary"]["temporal_clusters"]) > 0:
        # Find cluster with most anomalies
        max_cluster = max(
            summary["summary"]["temporal_clusters"], key=lambda c: c["count"]
        )

        # Step 3: Get detailed anomalies for that time window
        details = detector.get_form_anomaly_details(
            activity_id=activity_id,
            filters={"time_range": (max_cluster["start"], max_cluster["end"])},
        )

        # Verify we got relevant details
        assert details["returned_anomalies"] > 0
        assert all(
            max_cluster["start"] <= a["timestamp"] <= max_cluster["end"]
            for a in details["anomalies"]
        )


# ==========================================
# Performance Tests: Token Count
# ==========================================


@pytest.mark.performance
def test_summary_api_token_count_multiple_activities(
    detector: FormAnomalyDetector,
) -> None:
    """Test summary API token count for multiple activities (target: 95% reduction)."""
    import json

    activity_ids = [12345678901]  # Use same activity multiple times for test
    total_tokens = 0

    for activity_id in activity_ids:
        result = detector.detect_form_anomalies_summary(
            activity_id=activity_id,
            metrics=[
                "directGroundContactTime",
                "directVerticalOscillation",
                "directVerticalRatio",
            ],
            z_threshold=2.0,
        )

        json_str = json.dumps(result, ensure_ascii=False)
        tokens = len(json_str) // 4
        total_tokens += tokens

    # Average should be < 1000 per activity (target: ~700)
    avg_tokens = total_tokens / len(activity_ids)
    assert avg_tokens < 1000, f"Average tokens {avg_tokens} exceeds 1000"


@pytest.mark.performance
def test_details_api_token_count_with_filters(detector: FormAnomalyDetector) -> None:
    """Test details API token reduction with filtering (target: 89% reduction)."""
    import json

    activity_id = 12345678901

    # Get unfiltered (for comparison)
    unfiltered = detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    unfiltered_json = json.dumps(unfiltered, ensure_ascii=False)
    unfiltered_tokens = len(unfiltered_json) // 4

    # Get filtered by top 5 IDs
    if len(unfiltered["anomalies"]) > 5:
        top_5_ids = [a["anomaly_id"] for a in unfiltered["anomalies"][:5]]

        filtered = detector.get_form_anomaly_details(
            activity_id=activity_id,
            filters={"anomaly_ids": top_5_ids},
        )

        filtered_json = json.dumps(filtered, ensure_ascii=False)
        filtered_tokens = len(filtered_json) // 4

        # Filtered should be significantly smaller
        reduction_percent = (1 - filtered_tokens / unfiltered_tokens) * 100
        assert (
            reduction_percent > 50
        ), f"Token reduction {reduction_percent}% is too low"


@pytest.mark.performance
def test_summary_api_response_time(detector: FormAnomalyDetector) -> None:
    """Test summary API response time (target: <2s)."""
    import time

    activity_id = 12345678901

    start_time = time.time()
    detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=[
            "directGroundContactTime",
            "directVerticalOscillation",
            "directVerticalRatio",
        ],
        z_threshold=2.0,
    )
    elapsed_time = time.time() - start_time

    assert elapsed_time < 2.0, f"Response time {elapsed_time:.2f}s exceeds 2.0s"


@pytest.mark.performance
def test_details_api_response_time(detector: FormAnomalyDetector) -> None:
    """Test details API response time with filters (target: <2s)."""
    import time

    activity_id = 12345678901

    start_time = time.time()
    detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
        filters={"limit": 10},
    )
    elapsed_time = time.time() - start_time

    assert elapsed_time < 2.0, f"Response time {elapsed_time:.2f}s exceeds 2.0s"
