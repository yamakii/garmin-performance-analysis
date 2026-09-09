"""FormAnomalyDetector: apply_anomaly_filters()."""

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


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
