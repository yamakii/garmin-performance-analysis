"""Performance test: Token reduction measurement for Phase 4.

This test measures the token reduction achieved by using DuckDB-based
queries instead of JSON-based time series extraction.

Target: 90% token reduction (12.4k → <1k tokens)
"""

import json

import pytest

from tools.rag.queries.time_series_detail import TimeSeriesDetailExtractor


def count_tokens(data: dict) -> int:
    """Approximate token count by converting to JSON and counting characters.

    Rough estimate: 1 token ≈ 4 characters (OpenAI's rule of thumb).
    """
    json_str = json.dumps(data)
    return len(json_str) // 4


@pytest.mark.performance
def test_token_reduction_split_time_series():
    """Measure token reduction for get_split_time_series_detail.

    Compares:
    - JSON-based approach: Full time series returned (~12.4k tokens)
    - DuckDB-based approach: Statistics only (~1k tokens)

    Expected: ≥90% token reduction
    """
    extractor = TimeSeriesDetailExtractor()

    # Use real activity with data in DuckDB
    activity_id = 20594901208
    split_number = 1
    metrics = [
        "heart_rate",
        "speed",
        "cadence",
        "ground_contact_time",
        "vertical_oscillation",
        "vertical_ratio",
    ]

    # Test JSON-based approach (legacy)
    result_json = extractor.get_split_time_series_detail(
        activity_id=activity_id,
        split_number=split_number,
        metrics=metrics,
        use_duckdb=False,
    )

    # Test DuckDB-based approach (optimized - statistics only)
    result_duckdb = extractor.get_split_time_series_detail(
        activity_id=activity_id,
        split_number=split_number,
        metrics=metrics,
        use_duckdb=True,
        statistics_only=True,  # Only return statistics for max token reduction
    )

    # Measure token counts
    tokens_json = count_tokens(result_json)
    tokens_duckdb = count_tokens(result_duckdb)

    # Calculate reduction
    reduction_percent = ((tokens_json - tokens_duckdb) / tokens_json) * 100

    # Print results
    print(f"\n{'='*60}")
    print("Token Reduction Measurement - get_split_time_series_detail")
    print(f"{'='*60}")
    print(f"Activity ID: {activity_id}")
    print(f"Split: {split_number}")
    print(f"Metrics: {len(metrics)}")
    print("\nJSON-based approach:")
    print(f"  - Time series points: {len(result_json.get('time_series', []))}")
    print(f"  - Estimated tokens: {tokens_json:,}")
    print("\nDuckDB-based approach:")
    print(f"  - Time series points: {len(result_duckdb.get('time_series', []))}")
    print(f"  - Estimated tokens: {tokens_duckdb:,}")
    print("\nToken Reduction:")
    print(f"  - Absolute: {tokens_json - tokens_duckdb:,} tokens")
    print(f"  - Percentage: {reduction_percent:.1f}%")
    print("  - Target: ≥90%")
    print(f"  - Status: {'✅ PASS' if reduction_percent >= 90 else '❌ FAIL'}")
    print(f"{'='*60}\n")

    # Verify statistics are present in DuckDB result
    assert "statistics" in result_duckdb
    assert len(result_duckdb["statistics"]) == len(metrics)

    # Note: We don't compare exact statistics values because:
    # 1. JSON-based extraction may apply different unit conversions
    # 2. Different data extraction methods (JSON parsing vs DuckDB query)
    # The key metric is token reduction, which is the goal of this optimization

    # Assert target achieved
    assert (
        reduction_percent >= 90
    ), f"Token reduction {reduction_percent:.1f}% did not meet target of 90%"


@pytest.mark.performance
def test_token_reduction_statistics_only():
    """Measure token reduction when only statistics are needed (no time series).

    This is the optimal use case - we only want statistics, not the full time series.

    Expected: ≥95% token reduction
    """
    from tools.database.db_reader import GarminDBReader

    extractor = TimeSeriesDetailExtractor()
    db_reader = GarminDBReader()

    activity_id = 20594901208
    split_number = 1
    metrics = ["heart_rate", "speed", "cadence"]

    # Get time range
    start_time, end_time = extractor._get_split_time_range(activity_id, split_number)

    # JSON approach: Extract full time series, then calculate stats
    result_json = extractor.extract_metrics(
        activity_id=activity_id,
        start_time=start_time,
        end_time=end_time,
        metrics=metrics,
        use_duckdb=False,
    )
    stats_json = extractor.calculate_statistics(
        time_series_data=result_json["time_series"],
        metrics=metrics,
        use_duckdb=False,
    )

    # DuckDB approach: Get statistics directly from SQL
    stats_duckdb = db_reader.get_time_series_statistics(
        activity_id=activity_id,
        start_time_s=start_time,
        end_time_s=end_time,
        metrics=metrics,
    )

    # Measure token counts
    # For JSON: time series + statistics
    tokens_json = count_tokens(result_json) + count_tokens(stats_json)
    # For DuckDB: only statistics
    tokens_duckdb = count_tokens(stats_duckdb)

    reduction_percent = ((tokens_json - tokens_duckdb) / tokens_json) * 100

    print(f"\n{'='*60}")
    print("Token Reduction Measurement - Statistics Only")
    print(f"{'='*60}")
    print(f"Activity ID: {activity_id}")
    print(f"Time range: {start_time}-{end_time}s")
    print(f"Metrics: {len(metrics)}")
    print("\nJSON-based approach (time series + stats):")
    print(f"  - Estimated tokens: {tokens_json:,}")
    print("\nDuckDB-based approach (SQL statistics):")
    print(f"  - Estimated tokens: {tokens_duckdb:,}")
    print("\nToken Reduction:")
    print(f"  - Absolute: {tokens_json - tokens_duckdb:,} tokens")
    print(f"  - Percentage: {reduction_percent:.1f}%")
    print("  - Target: ≥95%")
    print(f"  - Status: {'✅ PASS' if reduction_percent >= 95 else '❌ FAIL'}")
    print(f"{'='*60}\n")

    assert (
        reduction_percent >= 95
    ), f"Token reduction {reduction_percent:.1f}% did not meet target of 95%"


@pytest.mark.performance
def test_query_speed_comparison():
    """Compare query speed: JSON parsing vs DuckDB SQL.

    Expected: DuckDB ≥5x faster than JSON parsing
    """
    import time

    extractor = TimeSeriesDetailExtractor()

    activity_id = 20594901208
    split_number = 1
    metrics = ["heart_rate", "speed", "cadence"]

    # Warm-up
    extractor.get_split_time_series_detail(
        activity_id=activity_id,
        split_number=split_number,
        metrics=metrics,
        use_duckdb=True,
    )

    # Measure JSON approach
    start = time.time()
    for _ in range(5):
        extractor.get_split_time_series_detail(
            activity_id=activity_id,
            split_number=split_number,
            metrics=metrics,
            use_duckdb=False,
        )
    json_time = (time.time() - start) / 5

    # Measure DuckDB approach
    start = time.time()
    for _ in range(5):
        extractor.get_split_time_series_detail(
            activity_id=activity_id,
            split_number=split_number,
            metrics=metrics,
            use_duckdb=True,
        )
    duckdb_time = (time.time() - start) / 5

    speedup = json_time / duckdb_time

    print(f"\n{'='*60}")
    print("Query Speed Comparison")
    print(f"{'='*60}")
    print(f"JSON approach: {json_time*1000:.2f}ms")
    print(f"DuckDB approach: {duckdb_time*1000:.2f}ms")
    print(f"Speedup: {speedup:.2f}x")
    print("Target: ≥5x")
    print(f"Status: {'✅ PASS' if speedup >= 5 else '⚠️  WARN (still functional)'}")
    print(f"{'='*60}\n")

    # Note: We don't assert on speed as it's hardware-dependent
    # But we print it for visibility
