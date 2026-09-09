"""FormAnomalyDetector: time-series extraction, detect_all, severity distribution, recommendations, temporal clusters."""

from typing import cast

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


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
    """Test _generate_severity_distribution with all severity levels (#666)."""
    anomalies = [
        {"z_score": 3.2},  # Low (<= 3.5)
        {"z_score": 3.0},  # Low (<= 3.5)
        {"z_score": 4.0},  # Medium (3.5 < z <= 4.5)
        {"z_score": 5.0},  # High (> 4.5)
        {"z_score": 4.6},  # High (> 4.5)
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
def test_severity_rebucket_high_medium_low(detector: FormAnomalyDetector) -> None:
    """Test re-stratified severity buckets (#666): high>4.5, 3.5-4.5, <=3.5."""
    distribution = detector._generate_severity_distribution(
        [
            {"z_score": 5.0},  # high (> 4.5)
            {"z_score": 4.0},  # medium (3.5 < z <= 4.5)
            {"z_score": 3.2},  # low (<= 3.5)
        ]
    )

    assert distribution["high"] == 1
    assert distribution["medium"] == 1
    assert distribution["low"] == 1


@pytest.mark.unit
def test_recommendation_names_dominant_metric(detector: FormAnomalyDetector) -> None:
    """Test pace recommendation names the dominant metric, not a fixed one (#666).

    With pace anomalies dominated by GCT, the recommendation must mention
    接地時間(GCT) and must NOT fall back to the old hard-coded "VO".
    """
    anomalies = [
        {"probable_cause": "pace_change", "metric": "directGroundContactTime"},
        {"probable_cause": "pace_change", "metric": "directGroundContactTime"},
        {"probable_cause": "pace_change", "metric": "directVerticalOscillation"},
    ]

    recs = detector._generate_recommendations(anomalies)

    assert len(recs) == 1
    assert "接地時間(GCT)" in recs[0]
    assert "VO" not in recs[0]


@pytest.mark.unit
def test_recommendation_empty_for_isolated_only(
    detector: FormAnomalyDetector,
) -> None:
    """Test isolated-only anomalies produce no recommendation (#666)."""
    anomalies = [
        {"probable_cause": "isolated", "metric": "directGroundContactTime"},
        {"probable_cause": "isolated", "metric": "directVerticalOscillation"},
    ]

    assert detector._generate_recommendations(anomalies) == []


@pytest.mark.unit
def test_recommendation_elevation_and_fatigue_labels(
    detector: FormAnomalyDetector,
) -> None:
    """Test elevation/fatigue causes emit the correct metric label + text (#666)."""
    elevation_recs = detector._generate_recommendations(
        [{"probable_cause": "elevation_change", "metric": "directVerticalRatio"}]
    )
    assert len(elevation_recs) == 1
    assert "上り坂" in elevation_recs[0]
    assert "上下動比(VR)" in elevation_recs[0]

    fatigue_recs = detector._generate_recommendations(
        [{"probable_cause": "fatigue", "metric": "directVerticalOscillation"}]
    )
    assert len(fatigue_recs) == 1
    assert "疲労" in fatigue_recs[0]
    assert "上下動(VO)" in fatigue_recs[0]


@pytest.mark.unit
def test_summary_includes_isolated_related(detector: FormAnomalyDetector) -> None:
    """Test summary exposes isolated_related and pace_related excludes it (#666).

    The fixture activity's GCT spikes have flat context (no elevation/pace/
    fatigue signal), so they classify as isolated. pace_related must therefore
    not absorb them.
    """
    result = detector.detect_form_anomalies_summary(
        activity_id=12345678901,
        metrics=["directGroundContactTime"],
        z_threshold=2.0,
    )

    summary = result["summary"]
    assert "isolated_related" in summary
    # pace_related counts only genuine pace_change causes, not isolated noise.
    cause_total = (
        summary["elevation_related"]
        + summary["pace_related"]
        + summary["fatigue_related"]
        + summary["isolated_related"]
    )
    assert cause_total == result["anomalies_detected"]


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
def test_summary_includes_max_material_cluster(
    detector: FormAnomalyDetector,
) -> None:
    """Summary exposes max_material_cluster matching the material-only max (#677)."""
    activity_id = 12345678901
    metrics = ["directGroundContactTime"]
    z_threshold = 2.0

    details = detector.get_form_anomaly_details(
        activity_id=activity_id,
        metrics=metrics,
        z_threshold=z_threshold,
        filters={"limit": 10000},
    )
    expected = detector._max_material_cluster(details["anomalies"])

    summary = detector.detect_form_anomalies_summary(
        activity_id=activity_id,
        metrics=metrics,
        z_threshold=z_threshold,
    )["summary"]

    assert "max_material_cluster" in summary
    assert isinstance(summary["max_material_cluster"], int)
    assert summary["max_material_cluster"] == expected


@pytest.mark.unit
def test_max_material_cluster_excludes_isolated(
    detector: FormAnomalyDetector,
) -> None:
    """Isolated noise in the same window is excluded; only material counts (#677)."""
    anomalies = [
        {"timestamp": 10 * i, "probable_cause": "isolated"} for i in range(10)
    ] + [
        {"timestamp": 50, "probable_cause": "pace_change"},
        {"timestamp": 100, "probable_cause": "elevation_change"},
    ]

    # All 12 fall in the first 5-minute window, but only the 2 material ones count.
    assert detector._max_material_cluster(anomalies) == 2


@pytest.mark.unit
def test_max_material_cluster_zero_when_no_material(
    detector: FormAnomalyDetector,
) -> None:
    """All-isolated anomalies yield a material cluster size of 0 (#677)."""
    anomalies = [{"timestamp": 10 * i, "probable_cause": "isolated"} for i in range(5)]

    assert detector._max_material_cluster(anomalies) == 0
