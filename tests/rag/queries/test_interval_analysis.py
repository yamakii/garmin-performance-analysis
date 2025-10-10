"""Test suite for IntervalAnalyzer.

This module tests the interval analysis functionality including:
- Work/Recovery interval detection
- Interval metrics aggregation
- Fatigue accumulation detection
- HR recovery speed calculation
"""

from typing import Any

import pytest

from tools.rag.queries.interval_analysis import IntervalAnalyzer


@pytest.fixture
def interval_analyzer():
    """Create IntervalAnalyzer instance for testing."""
    return IntervalAnalyzer()


@pytest.fixture
def mock_work_splits() -> list[dict]:
    """Mock splits data representing Work intervals (INTERVAL intensity)."""
    return [
        {
            "split_number": 1,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.0,
            "avg_hr_bpm": 175,
            "avg_gct_ms": 210,
            "avg_vo_cm": 7.8,
            "avg_vr_percent": 8.5,
            "start_time_s": 0,
            "end_time_s": 240,
        },
        {
            "split_number": 2,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.1,
            "avg_hr_bpm": 176,
            "avg_gct_ms": 212,
            "avg_vo_cm": 7.9,
            "avg_vr_percent": 8.6,
            "start_time_s": 240,
            "end_time_s": 480,
        },
    ]


@pytest.fixture
def mock_recovery_splits() -> list[dict]:
    """Mock splits data representing Recovery intervals (RECOVERY intensity)."""
    return [
        {
            "split_number": 3,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.5,
            "avg_hr_bpm": 145,
            "avg_gct_ms": 225,
            "avg_vo_cm": 8.2,
            "avg_vr_percent": 9.0,
            "start_time_s": 480,
            "end_time_s": 660,
        },
        {
            "split_number": 4,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.6,
            "avg_hr_bpm": 143,
            "avg_gct_ms": 227,
            "avg_vo_cm": 8.3,
            "avg_vr_percent": 9.1,
            "start_time_s": 660,
            "end_time_s": 840,
        },
    ]


@pytest.fixture
def mock_interval_splits(
    mock_work_splits: list[dict[str, Any]], mock_recovery_splits: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mock splits data with alternating Work/Recovery intervals."""
    return mock_work_splits + mock_recovery_splits


@pytest.mark.unit
def test_detect_intervals_work_recovery(
    interval_analyzer: IntervalAnalyzer, mock_interval_splits: list[dict]
):
    """Test Work/Recovery interval detection using intensity_type.

    Expected behavior:
    - INTERVAL intensity_type should be classified as Work
    - RECOVERY intensity_type should be classified as Recovery
    - Intervals should be properly segmented
    """
    intervals = interval_analyzer.detect_intervals(mock_interval_splits)

    # Should detect exactly 4 intervals
    assert len(intervals) == 4

    # First two should be work intervals (INTERVAL intensity)
    assert intervals[0]["segment_type"] == "work"
    assert intervals[1]["segment_type"] == "work"

    # Next two should be recovery intervals (RECOVERY intensity)
    assert intervals[2]["segment_type"] == "recovery"
    assert intervals[3]["segment_type"] == "recovery"


@pytest.mark.unit
def test_analyze_interval_metrics(
    interval_analyzer: IntervalAnalyzer, mock_work_splits: list[dict]
):
    """Test interval metrics aggregation (HR, pace, GCT, VO, VR).

    Expected behavior:
    - Should calculate average metrics across the interval
    - All metrics should be present in the result
    - Metrics should match expected values from input data
    """
    interval = {
        "segment_type": "work",
        "splits": mock_work_splits,
    }

    metrics = interval_analyzer.analyze_interval_metrics(interval, mock_work_splits)

    # Check all required metrics are present
    assert "avg_hr" in metrics
    assert "avg_pace" in metrics
    assert "avg_gct" in metrics
    assert "avg_vo" in metrics
    assert "avg_vr" in metrics

    # Verify calculated values are reasonable
    assert 170 < metrics["avg_hr"] < 180  # Average of 175, 176
    assert 4.0 <= metrics["avg_pace"] <= 4.2  # Average of 4.0, 4.1
    assert 210 <= metrics["avg_gct"] <= 215  # Average of 210, 212


@pytest.mark.unit
def test_detect_fatigue_accumulation(interval_analyzer: IntervalAnalyzer):
    """Test fatigue accumulation detection in final intervals.

    Expected behavior:
    - Compare first and last work intervals
    - Detect HR increase (fatigue indicator)
    - Detect pace degradation (fatigue indicator)
    - Return fatigue metrics
    """
    # Mock intervals with increasing fatigue
    intervals = [
        {
            "segment_type": "work",
            "avg_hr_bpm": 175,
            "avg_pace_min_per_km": 4.0,
            "avg_gct_ms": 210,
        },
        {
            "segment_type": "work",
            "avg_hr_bpm": 177,
            "avg_pace_min_per_km": 4.1,
            "avg_gct_ms": 212,
        },
        {
            "segment_type": "work",
            "avg_hr_bpm": 183,  # +8 bpm from first
            "avg_pace_min_per_km": 4.3,  # +0.3 min/km from first
            "avg_gct_ms": 218,  # +8 ms from first
        },
    ]

    fatigue = interval_analyzer.detect_fatigue(intervals)

    # Check fatigue indicators are detected
    assert "hr_increase_bpm" in fatigue
    assert "pace_degradation_sec_per_km" in fatigue
    assert "gct_degradation_ms" in fatigue

    # Verify fatigue values
    assert fatigue["hr_increase_bpm"] >= 5  # Significant HR increase
    assert fatigue["pace_degradation_sec_per_km"] > 0  # Pace got slower
    assert fatigue["gct_degradation_ms"] > 0  # GCT got worse


@pytest.mark.unit
def test_calculate_hr_recovery_speed(interval_analyzer: IntervalAnalyzer):
    """Test HR recovery speed calculation.

    Expected behavior:
    - Calculate HR drop from work to recovery
    - Return recovery rate in bpm/min
    - Handle different recovery durations
    """
    work_interval = {
        "segment_type": "work",
        "avg_hr_bpm": 175,
        "end_time_s": 300,
    }

    recovery_interval = {
        "segment_type": "recovery",
        "avg_hr_bpm": 145,
        "start_time_s": 300,
        "end_time_s": 480,  # 180 seconds = 3 minutes
    }

    recovery_speed = interval_analyzer.calculate_recovery_speed(
        work_interval, recovery_interval
    )

    # Recovery speed should be (175 - 145) / 3 = 10 bpm/min
    assert recovery_speed is not None
    assert 8 <= recovery_speed <= 12  # Allow some tolerance


@pytest.mark.unit
def test_interval_analysis_no_intervals(interval_analyzer: IntervalAnalyzer):
    """Test behavior when no intensity_type is set (normal run).

    Expected behavior:
    - Should return intervals with "steady" segment type
    - Should not crash or raise exceptions
    - Should provide meaningful feedback
    """
    # Mock steady-state run (no intensity_type)
    steady_splits = [
        {
            "split_number": i,
            "intensity_type": None,
            "avg_pace_min_per_km": 5.0,
            "avg_hr_bpm": 155,
            "avg_gct_ms": 220,
            "avg_vo_cm": 8.0,
            "avg_vr_percent": 8.8,
            "start_time_s": i * 240,
            "end_time_s": (i + 1) * 240,
        }
        for i in range(5)
    ]

    result = interval_analyzer.detect_intervals(steady_splits)

    # Should handle gracefully - return 5 steady intervals
    assert isinstance(result, list)
    assert len(result) == 5

    # All should be classified as steady (None intensity_type)
    for interval in result:
        assert interval["segment_type"] == "steady"


@pytest.mark.unit
def test_interval_analysis_with_warmup_cooldown(interval_analyzer: IntervalAnalyzer):
    """Test interval detection with warmup and cooldown phases using intensity_type.

    Expected behavior:
    - Detect warmup (WARMUP intensity_type)
    - Detect main work intervals (INTERVAL intensity_type)
    - Detect recovery (RECOVERY intensity_type)
    - Detect cooldown (COOLDOWN intensity_type)
    - Properly classify each phase
    """
    # Mock splits with warmup, work, recovery, cooldown
    splits = [
        # Warmup
        {
            "split_number": 1,
            "intensity_type": "WARMUP",
            "avg_pace_min_per_km": 6.0,
            "avg_hr_bpm": 130,
            "start_time_s": 0,
            "end_time_s": 300,
        },
        # Work
        {
            "split_number": 2,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.0,
            "avg_hr_bpm": 175,
            "start_time_s": 300,
            "end_time_s": 540,
        },
        # Recovery
        {
            "split_number": 3,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.5,
            "avg_hr_bpm": 145,
            "start_time_s": 540,
            "end_time_s": 720,
        },
        # Cooldown
        {
            "split_number": 4,
            "intensity_type": "COOLDOWN",
            "avg_pace_min_per_km": 6.5,
            "avg_hr_bpm": 125,
            "start_time_s": 720,
            "end_time_s": 1020,
        },
    ]

    intervals = interval_analyzer.detect_intervals(splits)

    # Should detect exactly 4 segments
    assert len(intervals) == 4

    # Check segment types match intensity_type mapping
    assert intervals[0]["segment_type"] == "warmup"
    assert intervals[1]["segment_type"] == "work"
    assert intervals[2]["segment_type"] == "recovery"
    assert intervals[3]["segment_type"] == "cooldown"


@pytest.mark.integration
def test_interval_analysis_real_activity(interval_analyzer: IntervalAnalyzer):
    """Integration test with fixture interval training data using intensity_type.

    Uses realistic interval training data to test the full analysis pipeline.
    """
    # Create realistic interval training splits (warmup + 3x work/recovery + cooldown)
    interval_training_splits = [
        # Warmup
        {
            "split_number": 1,
            "intensity_type": "WARMUP",
            "avg_pace_min_per_km": 6.0,
            "avg_hr_bpm": 130,
            "avg_gct_ms": 240,
            "avg_vo_cm": 8.5,
            "avg_vr_percent": 9.2,
            "start_time_s": 0,
            "end_time_s": 300,
        },
        # Work 1
        {
            "split_number": 2,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.0,
            "avg_hr_bpm": 175,
            "avg_gct_ms": 210,
            "avg_vo_cm": 7.8,
            "avg_vr_percent": 8.5,
            "start_time_s": 300,
            "end_time_s": 540,
        },
        # Recovery 1
        {
            "split_number": 3,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.5,
            "avg_hr_bpm": 145,
            "avg_gct_ms": 225,
            "avg_vo_cm": 8.2,
            "avg_vr_percent": 9.0,
            "start_time_s": 540,
            "end_time_s": 720,
        },
        # Work 2
        {
            "split_number": 4,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.1,
            "avg_hr_bpm": 177,
            "avg_gct_ms": 212,
            "avg_vo_cm": 7.9,
            "avg_vr_percent": 8.6,
            "start_time_s": 720,
            "end_time_s": 960,
        },
        # Recovery 2
        {
            "split_number": 5,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.6,
            "avg_hr_bpm": 143,
            "avg_gct_ms": 227,
            "avg_vo_cm": 8.3,
            "avg_vr_percent": 9.1,
            "start_time_s": 960,
            "end_time_s": 1140,
        },
        # Work 3
        {
            "split_number": 6,
            "intensity_type": "INTERVAL",
            "avg_pace_min_per_km": 4.2,
            "avg_hr_bpm": 180,
            "avg_gct_ms": 215,
            "avg_vo_cm": 8.0,
            "avg_vr_percent": 8.7,
            "start_time_s": 1140,
            "end_time_s": 1380,
        },
        # Recovery 3
        {
            "split_number": 7,
            "intensity_type": "RECOVERY",
            "avg_pace_min_per_km": 5.7,
            "avg_hr_bpm": 140,
            "avg_gct_ms": 230,
            "avg_vo_cm": 8.4,
            "avg_vr_percent": 9.2,
            "start_time_s": 1380,
            "end_time_s": 1560,
        },
        # Cooldown
        {
            "split_number": 8,
            "intensity_type": "COOLDOWN",
            "avg_pace_min_per_km": 6.5,
            "avg_hr_bpm": 125,
            "avg_gct_ms": 245,
            "avg_vo_cm": 8.8,
            "avg_vr_percent": 9.5,
            "start_time_s": 1560,
            "end_time_s": 1860,
        },
    ]

    # Test full interval analysis pipeline
    intervals = interval_analyzer.detect_intervals(interval_training_splits)

    # Should detect exactly 8 intervals
    assert len(intervals) == 8

    # Verify correct segment type distribution
    segment_types = [interval["segment_type"] for interval in intervals]
    assert segment_types.count("work") == 3
    assert segment_types.count("recovery") == 3
    assert segment_types.count("warmup") == 1
    assert segment_types.count("cooldown") == 1

    # Should detect fatigue
    work_intervals = [i for i in intervals if i.get("segment_type") == "work"]
    fatigue = interval_analyzer.detect_fatigue(work_intervals)
    assert fatigue is not None
    assert "hr_increase_bpm" in fatigue
    assert "pace_degradation_sec_per_km" in fatigue
