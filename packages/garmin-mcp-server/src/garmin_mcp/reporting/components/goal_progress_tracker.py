"""Track progress toward race goals using VDOT predictions.

Uses standard VDOT race time prediction table with linear interpolation
between known reference points.
"""

from typing import Any

# VDOT reference table: {vdot: {distance: time_in_seconds}}
# Calibrated reference points based on Jack Daniels' VDOT Running Formula.
# Distances: 5K, 10K, half_marathon (half), marathon (full)
_VDOT_TABLE: dict[int, dict[str, int]] = {
    30: {"5k": 2400, "10k": 4980, "half": 11100, "full": 23220},
    35: {"5k": 2058, "10k": 4278, "half": 9540, "full": 19920},
    40: {"5k": 1800, "10k": 3738, "half": 8310, "full": 17340},
    45: {"5k": 1410, "10k": 2940, "half": 6480, "full": 13680},
    50: {"5k": 1230, "10k": 2556, "half": 5640, "full": 11880},
    55: {"5k": 1086, "10k": 2256, "half": 4986, "full": 10440},
    60: {"5k": 966, "10k": 2004, "half": 4434, "full": 9264},
    65: {"5k": 864, "10k": 1794, "half": 3966, "full": 8280},
    70: {"5k": 780, "10k": 1620, "half": 3576, "full": 7464},
    75: {"5k": 702, "10k": 1458, "half": 3222, "full": 6720},
    80: {"5k": 636, "10k": 1320, "half": 2916, "full": 6084},
    85: {"5k": 576, "10k": 1194, "half": 2640, "full": 5508},
}

# Sorted VDOT keys for interpolation
_VDOT_KEYS = sorted(_VDOT_TABLE.keys())

# Distance name mapping for display
_DISTANCE_DISPLAY: dict[str, str] = {
    "5k": "5K",
    "10k": "10K",
    "half": "Half",
    "full": "Full",
}


def _interpolate(vdot: float, distance: str) -> int:
    """Interpolate race time for a given VDOT and distance.

    Uses linear interpolation between known VDOT reference points.

    Args:
        vdot: VDOT value (typically 30-85).
        distance: Race distance key ("5k", "10k", "half", "full").

    Returns:
        Predicted time in seconds.
    """
    # Clamp to table range
    if vdot <= _VDOT_KEYS[0]:
        return _VDOT_TABLE[_VDOT_KEYS[0]][distance]
    if vdot >= _VDOT_KEYS[-1]:
        return _VDOT_TABLE[_VDOT_KEYS[-1]][distance]

    # Find bracketing VDOT values
    for i in range(len(_VDOT_KEYS) - 1):
        low = _VDOT_KEYS[i]
        high = _VDOT_KEYS[i + 1]
        if low <= vdot <= high:
            frac = (vdot - low) / (high - low)
            time_low = _VDOT_TABLE[low][distance]
            time_high = _VDOT_TABLE[high][distance]
            return round(time_low + frac * (time_high - time_low))

    return _VDOT_TABLE[_VDOT_KEYS[-1]][distance]


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
            plan_data: Training plan dict with goal_type, goal_time_seconds,
                       goal_distance, and optionally weeks_remaining.

        Returns:
            Goal dict with distance, target_seconds, and weeks_remaining,
            or None if no race goal exists.
        """
        if not plan_data:
            return None

        goal_type = plan_data.get("goal_type", "")
        if goal_type != "race":
            return None

        goal_time = plan_data.get("goal_time_seconds")
        goal_distance = plan_data.get("goal_distance")

        if not goal_time or not goal_distance:
            return None

        return {
            "distance": goal_distance,
            "target_seconds": goal_time,
            "weeks_remaining": plan_data.get("weeks_remaining"),
        }

    def predict_race_time(self, vdot: float, distance: str) -> int:
        """Predict race time from current VDOT.

        Args:
            vdot: Current VDOT value.
            distance: Race distance ("5k", "10k", "half", "full").

        Returns:
            Predicted time in seconds.
        """
        return _interpolate(vdot, distance)

    def calculate_progress(
        self, goal: dict[str, Any] | None, current_vdot: float
    ) -> dict[str, Any] | None:
        """Calculate gap between predicted and goal time.

        Args:
            goal: Goal dict from get_active_plan_goal().
            current_vdot: Current VDOT value.

        Returns:
            Progress dict with predicted_seconds, gap_seconds,
            pace_gap_per_km, and formatted strings, or None.
        """
        if not goal:
            return None

        distance = goal["distance"]
        target_seconds = goal["target_seconds"]
        predicted_seconds = self.predict_race_time(current_vdot, distance)

        gap_seconds = predicted_seconds - target_seconds

        # Calculate pace gap per km
        distance_km_map: dict[str, float] = {
            "5k": 5.0,
            "10k": 10.0,
            "half": 21.0975,
            "full": 42.195,
        }
        distance_km = distance_km_map.get(distance, 10.0)
        pace_gap_per_km = gap_seconds / distance_km

        display_distance = _DISTANCE_DISPLAY.get(distance, distance)
        weeks_remaining = goal.get("weeks_remaining")

        weeks_text = ""
        if weeks_remaining is not None:
            weeks_text = f" (残り{weeks_remaining}週間)"

        return {
            "distance": distance,
            "distance_display": display_distance,
            "target_seconds": target_seconds,
            "target_formatted": _format_time(target_seconds),
            "predicted_seconds": predicted_seconds,
            "predicted_formatted": _format_time(predicted_seconds),
            "current_vdot": current_vdot,
            "gap_seconds": gap_seconds,
            "pace_gap_per_km": round(pace_gap_per_km, 1),
            "weeks_remaining": weeks_remaining,
            "summary_ja": (
                f"{display_distance}目標: {_format_time(target_seconds)}{weeks_text}\n"
                f"現在の予測: {_format_time(predicted_seconds)} (VDOT {current_vdot})\n"
                f"ギャップ: {gap_seconds:+d}秒 → "
                f"ペースをあと{abs(pace_gap_per_km):.0f}秒/km"
                f"{'改善する必要あり' if gap_seconds > 0 else '余裕あり'}"
            ),
        }
