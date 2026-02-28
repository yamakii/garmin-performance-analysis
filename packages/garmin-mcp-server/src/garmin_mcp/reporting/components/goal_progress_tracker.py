"""Track progress toward race goals using VDOT predictions.

Uses Jack Daniels' VDOT tables to predict race times from current VO2max,
then calculates the gap between predicted and goal times.
"""

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# VDOT reference table: vdot -> {distance: time_in_seconds}
# Based on Jack Daniels' Running Formula tables.
# Distances: 5K, 10K, Half Marathon (21.0975km), Full Marathon (42.195km)
_VDOT_TABLE: dict[int, dict[str, int]] = {
    30: {"5K": 2100, "10K": 4370, "half": 9780, "full": 20580},
    32: {"5K": 1980, "10K": 4120, "half": 9225, "full": 19410},
    34: {"5K": 1870, "10K": 3890, "half": 8710, "full": 18350},
    36: {"5K": 1770, "10K": 3680, "half": 8240, "full": 17380},
    38: {"5K": 1680, "10K": 3490, "half": 7815, "full": 16490},
    40: {"5K": 1598, "10K": 3318, "half": 7428, "full": 15672},
    42: {"5K": 1522, "10K": 3160, "half": 7074, "full": 14918},
    44: {"5K": 1452, "10K": 3014, "half": 6746, "full": 14222},
    46: {"5K": 1370, "10K": 2848, "half": 6376, "full": 13440},
    48: {"5K": 1310, "10K": 2722, "half": 6060, "full": 12780},
    50: {"5K": 1255, "10K": 2606, "half": 5810, "full": 12250},
    52: {"5K": 1220, "10K": 2534, "half": 5672, "full": 11964},
    54: {"5K": 1172, "10K": 2434, "half": 5450, "full": 11498},
    56: {"5K": 1127, "10K": 2340, "half": 5240, "full": 11060},
    58: {"5K": 1085, "10K": 2254, "half": 5046, "full": 10650},
    60: {"5K": 1046, "10K": 2172, "half": 4864, "full": 10268},
    62: {"5K": 1009, "10K": 2096, "half": 4694, "full": 9910},
    64: {"5K": 975, "10K": 2024, "half": 4532, "full": 9572},
    66: {"5K": 943, "10K": 1958, "half": 4384, "full": 9254},
    68: {"5K": 913, "10K": 1896, "half": 4244, "full": 8956},
    70: {"5K": 885, "10K": 1838, "half": 4114, "full": 8678},
}

# GoalType -> (distance label, distance in km)
_GOAL_TYPE_MAP: dict[str, tuple[str, float]] = {
    "race_5k": ("5K", 5.0),
    "race_10k": ("10K", 10.0),
    "race_half": ("half", 21.0975),
    "race_full": ("full", 42.195),
}

_VALID_DISTANCES = {"5K", "10K", "half", "full"}


def _interpolate_time(vdot: float, distance: str) -> int:
    """Interpolate race time from VDOT table using linear interpolation.

    Args:
        vdot: Current VDOT value.
        distance: Race distance key ("5K", "10K", "half", "full").

    Returns:
        Predicted time in seconds (rounded to nearest integer).
    """
    sorted_vdots = sorted(_VDOT_TABLE.keys())

    # Clamp to table range
    if vdot <= sorted_vdots[0]:
        return _VDOT_TABLE[sorted_vdots[0]][distance]
    if vdot >= sorted_vdots[-1]:
        return _VDOT_TABLE[sorted_vdots[-1]][distance]

    # Find bracketing VDOT values
    lower_vdot = sorted_vdots[0]
    upper_vdot = sorted_vdots[-1]
    for v in sorted_vdots:
        if v <= vdot:
            lower_vdot = v
        if v >= vdot:
            upper_vdot = v
            break

    if lower_vdot == upper_vdot:
        return _VDOT_TABLE[lower_vdot][distance]

    # Linear interpolation
    fraction = (vdot - lower_vdot) / (upper_vdot - lower_vdot)
    lower_time = _VDOT_TABLE[lower_vdot][distance]
    upper_time = _VDOT_TABLE[upper_vdot][distance]
    interpolated = lower_time + fraction * (upper_time - lower_time)
    return round(interpolated)


def _format_time(seconds: int) -> str:
    """Format seconds as H:MM:SS or MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class GoalProgressTracker:
    """Track progress toward race goals using VDOT predictions."""

    def get_active_plan_goal(
        self, plan_data: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Get goal from active training plan data.

        Args:
            plan_data: Training plan dict (from get_training_plan MCP tool),
                       or None if no active plan.

        Returns:
            Goal dict with goal_type, goal_time_seconds, distance, distance_km,
            or None if no race goal.
        """
        if plan_data is None:
            return None

        goal_type = plan_data.get("goal_type", "")
        target_time_seconds = plan_data.get("target_time_seconds")

        # Only race goals have progress tracking
        if goal_type not in _GOAL_TYPE_MAP:
            return None

        # Must have a target time to track progress
        if target_time_seconds is None:
            return None

        distance, distance_km = _GOAL_TYPE_MAP[goal_type]
        return {
            "goal_type": goal_type,
            "goal_time_seconds": target_time_seconds,
            "distance": distance,
            "distance_km": distance_km,
        }

    def predict_race_time(self, vdot: float, distance: str) -> int:
        """Predict race time from current VDOT.

        Args:
            vdot: Current VDOT value.
            distance: Race distance ("5K", "10K", "half", "full").

        Returns:
            Predicted time in seconds.

        Raises:
            ValueError: If distance is not valid.
        """
        if distance not in _VALID_DISTANCES:
            raise ValueError(
                f"Invalid distance '{distance}'. Must be one of: {_VALID_DISTANCES}"
            )
        return _interpolate_time(vdot, distance)

    def calculate_progress(
        self, goal: dict[str, Any] | None, current_vdot: float
    ) -> dict[str, Any] | None:
        """Calculate gap between predicted and goal time.

        Args:
            goal: Goal dict from get_active_plan_goal(), or None.
            current_vdot: Current VDOT from VO2max data.

        Returns:
            Progress dict with predicted time, gap, pace gap, etc.
            None if no goal provided.
        """
        if goal is None:
            return None

        distance = goal["distance"]
        distance_km = goal["distance_km"]
        goal_time_seconds = goal["goal_time_seconds"]

        predicted_seconds = self.predict_race_time(current_vdot, distance)

        gap_seconds = goal_time_seconds - predicted_seconds
        pace_gap_per_km = math.copysign(abs(gap_seconds) / distance_km, gap_seconds)

        return {
            "predicted_time_seconds": predicted_seconds,
            "predicted_time_formatted": _format_time(predicted_seconds),
            "goal_time_seconds": goal_time_seconds,
            "goal_time_formatted": _format_time(goal_time_seconds),
            "gap_seconds": gap_seconds,
            "pace_gap_per_km": round(pace_gap_per_km, 1),
            "distance": distance,
            "distance_km": distance_km,
            "current_vdot": current_vdot,
        }
