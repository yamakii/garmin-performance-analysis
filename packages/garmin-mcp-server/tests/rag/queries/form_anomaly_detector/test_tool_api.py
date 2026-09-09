"""detect_form_anomalies_summary / get_form_anomaly_details tool API: structure, filters, workflow, token and response-time budgets."""

import json

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


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
    assert "pace_related" in summary
    assert "fatigue_related" in summary
    assert "isolated_related" in summary  # #666
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


@pytest.mark.performance
def test_summary_api_token_count_multiple_activities(
    detector: FormAnomalyDetector,
) -> None:
    """Test summary API token count for multiple activities (target: 95% reduction)."""

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
