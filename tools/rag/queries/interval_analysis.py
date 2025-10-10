"""Interval analysis tools for detecting and analyzing Work/Recovery segments.

This module provides functionality to:
- Detect Work/Recovery intervals from pace changes
- Calculate interval metrics (HR, pace, GCT, VO, VR)
- Detect fatigue accumulation
- Calculate HR recovery speed
"""

import statistics
from typing import Any


class IntervalAnalyzer:
    """Analyzer for interval training data.

    Detects Work/Recovery segments from pace changes and calculates
    comprehensive metrics for each interval.
    """

    def __init__(self):
        """Initialize IntervalAnalyzer."""
        pass

    def detect_intervals(
        self,
        splits: list[dict],
        pace_threshold_factor: float = 1.3,
        min_work_duration: int = 180,
        min_recovery_duration: int = 60,
    ) -> list[dict[str, Any]]:
        """Detect Work/Recovery intervals from pace changes.

        Args:
            splits: List of split data with pace and HR information
            pace_threshold_factor: Recovery/Work pace ratio (default 1.3)
            min_work_duration: Minimum work interval duration in seconds
            min_recovery_duration: Minimum recovery interval duration in seconds

        Returns:
            List of detected intervals with segment type and metrics
        """
        if not splits:
            return []

        intervals = []

        # Calculate overall pace statistics to determine thresholds
        paces = [
            split["avg_pace_min_per_km"]
            for split in splits
            if "avg_pace_min_per_km" in split
        ]

        if not paces:
            return []

        avg_pace = statistics.mean(paces)
        pace_std = statistics.stdev(paces) if len(paces) > 1 else 0

        # Threshold for detecting work vs recovery
        # Work: faster than average - 0.5 std
        # Recovery: slower than average + 0.3 std (adjusted for better detection)
        work_threshold = avg_pace - 0.5 * pace_std
        recovery_threshold = avg_pace + 0.3 * pace_std

        # Detect intervals based on pace
        for i, split in enumerate(splits):
            pace = split.get("avg_pace_min_per_km", avg_pace)
            duration = split.get("end_time_s", 0) - split.get("start_time_s", 0)
            split_number = split.get("split_number", i + 1)

            # Classify segment type
            # First check for warmup/cooldown based on position and pace
            if split_number == 1 and pace > 5.5:
                segment_type = "warmup"
            elif split_number == len(splits) and pace > 6.0:
                segment_type = "cooldown"
            # Then check pace thresholds for work/recovery
            elif pace < work_threshold:
                segment_type = "work"
            elif pace > recovery_threshold:
                segment_type = "recovery"
            # Handle edge cases based on absolute pace values
            elif pace < 4.5:
                # Very fast pace - definitely work
                segment_type = "work"
            elif pace > 5.3:
                # Moderate-slow pace - likely recovery if not first/last
                if split_number == 1:
                    segment_type = "warmup"
                elif split_number == len(splits):
                    segment_type = "cooldown"
                else:
                    segment_type = "recovery"
            elif pace < 5.0:
                # Fast but not work - could be warmup or tempo
                segment_type = "warmup" if split_number == 1 else "work"
            else:
                segment_type = "steady"

            # Add interval
            interval = {
                "segment_number": split_number,
                "segment_type": segment_type,
                "start_time": split.get("start_time_s", 0),
                "end_time": split.get("end_time_s", 0),
                "duration_seconds": duration,
                "avg_pace_min_per_km": pace,
                "avg_hr_bpm": split.get("avg_hr_bpm", 0),
                "avg_gct_ms": split.get("avg_gct_ms", 0),
                "avg_vo_cm": split.get("avg_vo_cm", 0),
                "avg_vr_percent": split.get("avg_vr_percent", 0),
            }

            intervals.append(interval)

        return intervals

    def analyze_interval_metrics(
        self, interval: dict, splits: list[dict]
    ) -> dict[str, Any]:
        """Calculate aggregate metrics for an interval.

        Args:
            interval: Interval definition with segment type
            splits: Split data for the interval

        Returns:
            Dictionary with average metrics (HR, pace, GCT, VO, VR)
        """
        if not splits:
            return {}

        # Calculate averages
        metrics = {
            "avg_hr": statistics.mean([s.get("avg_hr_bpm", 0) for s in splits]),
            "avg_pace": statistics.mean(
                [s.get("avg_pace_min_per_km", 0) for s in splits]
            ),
            "avg_gct": statistics.mean([s.get("avg_gct_ms", 0) for s in splits]),
            "avg_vo": statistics.mean([s.get("avg_vo_cm", 0) for s in splits]),
            "avg_vr": statistics.mean([s.get("avg_vr_percent", 0) for s in splits]),
        }

        return metrics

    def detect_fatigue(self, intervals: list[dict]) -> dict[str, Any]:
        """Detect fatigue accumulation by comparing first and last intervals.

        Args:
            intervals: List of work intervals to analyze

        Returns:
            Dictionary with fatigue indicators (HR increase, pace/GCT degradation)
        """
        if len(intervals) < 2:
            return {
                "hr_increase_bpm": 0,
                "pace_degradation_sec_per_km": 0,
                "gct_degradation_ms": 0,
            }

        # Filter work intervals only
        work_intervals = [i for i in intervals if i.get("segment_type") == "work"]

        if len(work_intervals) < 2:
            return {
                "hr_increase_bpm": 0,
                "pace_degradation_sec_per_km": 0,
                "gct_degradation_ms": 0,
            }

        first = work_intervals[0]
        last = work_intervals[-1]

        # Calculate fatigue indicators
        hr_increase = last.get("avg_hr_bpm", 0) - first.get("avg_hr_bpm", 0)
        pace_degradation = (
            last.get("avg_pace_min_per_km", 0) - first.get("avg_pace_min_per_km", 0)
        ) * 60  # Convert to seconds per km
        gct_degradation = last.get("avg_gct_ms", 0) - first.get("avg_gct_ms", 0)

        return {
            "hr_increase_bpm": hr_increase,
            "pace_degradation_sec_per_km": pace_degradation,
            "gct_degradation_ms": gct_degradation,
        }

    def calculate_recovery_speed(
        self, work_interval: dict, recovery_interval: dict
    ) -> float | None:
        """Calculate HR recovery speed (bpm/min).

        Args:
            work_interval: Work interval with ending HR
            recovery_interval: Recovery interval with starting HR

        Returns:
            HR recovery rate in bpm/min, or None if cannot calculate
        """
        work_hr = work_interval.get("avg_hr_bpm")
        recovery_hr = recovery_interval.get("avg_hr_bpm")

        if work_hr is None or recovery_hr is None:
            return None

        # Calculate recovery duration in minutes
        # Try both naming conventions (end_time_s and end_time)
        recovery_duration_s = recovery_interval.get(
            "end_time_s", recovery_interval.get("end_time", 0)
        ) - recovery_interval.get(
            "start_time_s", recovery_interval.get("start_time", 0)
        )
        recovery_duration_min = float(recovery_duration_s) / 60.0

        if recovery_duration_min <= 0:
            return None

        # Calculate recovery rate
        hr_drop = float(work_hr) - float(recovery_hr)
        recovery_rate = hr_drop / recovery_duration_min

        return float(recovery_rate)
