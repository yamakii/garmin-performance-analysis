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
    ) -> list[dict[str, Any]]:
        """Detect Work/Recovery intervals from intensity_type in DuckDB.

        Args:
            splits: List of split data with intensity_type and metrics

        Returns:
            List of detected intervals with segment type and metrics
        """
        if not splits:
            return []

        intervals = []

        # Process each split using intensity_type
        for i, split in enumerate(splits):
            intensity_type = split.get("intensity_type")
            duration = split.get("end_time_s", 0) - split.get("start_time_s", 0)
            split_number = split.get("split_number", i + 1)

            # Map intensity_type to segment_type
            if intensity_type == "INTERVAL":
                segment_type = "work"
            elif intensity_type == "RECOVERY":
                segment_type = "recovery"
            elif intensity_type == "WARMUP":
                segment_type = "warmup"
            elif intensity_type == "COOLDOWN":
                segment_type = "cooldown"
            else:
                # For None or unknown intensity types, use "steady"
                segment_type = "steady"

            # Create interval
            interval = {
                "segment_number": split_number,
                "segment_type": segment_type,
                "start_time": split.get("start_time_s", 0),
                "end_time": split.get("end_time_s", 0),
                "duration_seconds": duration,
                "avg_pace_min_per_km": split.get("avg_pace_min_per_km", 0),
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

    def get_interval_analysis(
        self,
        activity_id: int,
    ) -> dict[str, Any]:
        """Get comprehensive interval training analysis.

        Args:
            activity_id: Activity ID.

        Returns:
            Dictionary with interval analysis:
            {
                "activity_id": int,
                "segments": [
                    {
                        "segment_number": int,
                        "segment_type": str,
                        ...
                    },
                    ...
                ],
                "work_recovery_comparison": {...},
                "fatigue_indicators": {...}
            }
        """
        from garmin_mcp.database.connection import get_connection
        from garmin_mcp.database.db_reader import GarminDBReader

        # Query DuckDB directly for splits with intensity_type and time ranges
        db_reader = GarminDBReader()

        try:
            with get_connection(db_reader.db_path) as conn:
                result = conn.execute(
                    """
                    SELECT
                        split_index,
                        distance,
                        start_time_s,
                        end_time_s,
                        intensity_type,
                        pace_seconds_per_km,
                        heart_rate,
                        ground_contact_time,
                        vertical_oscillation,
                        vertical_ratio
                    FROM splits
                    WHERE activity_id = ?
                    ORDER BY split_index
                    """,
                    [activity_id],
                ).fetchall()

            if not result:
                return {
                    "activity_id": activity_id,
                    "segments": [],
                    "error": f"No splits data found in DuckDB for activity {activity_id}",
                }

            # Convert to splits format
            splits = []
            for row in result:
                split_data = {
                    "split_number": row[0],
                    "distance_km": row[1],
                    "start_time_s": row[2],
                    "end_time_s": row[3],
                    "intensity_type": row[4],
                    "avg_pace_min_per_km": (
                        row[5] / 60.0 if row[5] else 0
                    ),  # Convert seconds/km to minutes/km
                    "avg_hr_bpm": row[6] if row[6] else 0,
                    "avg_gct_ms": row[7] if row[7] else 0,
                    "avg_vo_cm": row[8] if row[8] else 0,
                    "avg_vr_percent": row[9] if row[9] else 0,
                }
                splits.append(split_data)

        except Exception as e:
            return {
                "activity_id": activity_id,
                "segments": [],
                "error": f"Error querying DuckDB: {e}",
            }

        if not splits:
            return {
                "activity_id": activity_id,
                "segments": [],
                "message": "No splits data available for interval analysis",
            }

        # Detect intervals using intensity_type
        intervals = self.detect_intervals(splits)

        # Calculate fatigue indicators
        fatigue = self.detect_fatigue(intervals)

        # Calculate work/recovery comparison
        work_intervals = [i for i in intervals if i.get("segment_type") == "work"]
        recovery_intervals = [
            i for i in intervals if i.get("segment_type") == "recovery"
        ]

        work_recovery_comparison = {}
        if work_intervals and recovery_intervals:
            work_recovery_comparison = {
                "work_count": len(work_intervals),
                "recovery_count": len(recovery_intervals),
                "avg_work_pace": statistics.mean(
                    [w.get("avg_pace_min_per_km", 0) for w in work_intervals]
                ),
                "avg_recovery_pace": statistics.mean(
                    [r.get("avg_pace_min_per_km", 0) for r in recovery_intervals]
                ),
                "avg_work_hr": statistics.mean(
                    [w.get("avg_hr_bpm", 0) for w in work_intervals]
                ),
                "avg_recovery_hr": statistics.mean(
                    [r.get("avg_hr_bpm", 0) for r in recovery_intervals]
                ),
            }

            # Calculate HR recovery rates
            recovery_rates = []
            for i in range(len(work_intervals)):
                if i < len(recovery_intervals):
                    rate = self.calculate_recovery_speed(
                        work_intervals[i], recovery_intervals[i]
                    )
                    if rate is not None:
                        recovery_rates.append(rate)

            if recovery_rates:
                work_recovery_comparison["avg_hr_recovery_rate_bpm_per_min"] = (
                    statistics.mean(recovery_rates)
                )

        return {
            "activity_id": activity_id,
            "segments": intervals,
            "work_recovery_comparison": work_recovery_comparison,
            "fatigue_indicators": fatigue,
        }
