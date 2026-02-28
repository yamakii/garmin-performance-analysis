"""Track progress toward race goals using VDOT predictions."""

from __future__ import annotations

import datetime
from typing import Any

from garmin_mcp.training_plan.vdot import VDOTCalculator

DISTANCE_MAP: dict[str, float] = {
    "race_5k": 5.0,
    "5k": 5.0,
    "race_10k": 10.0,
    "10k": 10.0,
    "race_half": 21.0975,
    "half": 21.0975,
    "race_full": 42.195,
    "full": 42.195,
}

GOAL_TYPE_JA: dict[str, str] = {
    "race_5k": "5K目標",
    "race_10k": "10K目標",
    "race_half": "ハーフ目標",
    "race_full": "フル目標",
}


def _format_time(seconds: int) -> str:
    """Format seconds to human-readable time string."""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class GoalProgressTracker:
    """Track progress toward race goals using VDOT predictions."""

    def get_active_plan_goal(
        self, plan_data: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Get goal from active training plan data.

        Extract goal_type, target_time_seconds, target_race_date from plan_data.
        Return None if plan_data is None, or if goal_type starts with
        'fitness' or 'return_to_run'.
        """
        if plan_data is None:
            return None

        goal_type = plan_data.get("goal_type", "")
        if not goal_type:
            return None

        if goal_type.startswith("fitness") or goal_type.startswith("return_to_run"):
            return None

        target_time_seconds = plan_data.get("target_time_seconds")
        if target_time_seconds is None:
            return None

        result: dict[str, Any] = {
            "goal_type": goal_type,
            "target_time_seconds": int(target_time_seconds),
        }

        target_race_date = plan_data.get("target_race_date")
        if target_race_date is not None:
            result["target_race_date"] = str(target_race_date)

        return result

    def predict_race_time(self, vdot: float, distance: str) -> int:
        """Predict race time from current VDOT. Returns seconds.

        Uses VDOTCalculator to predict race time for the given distance.
        """
        distance_km = DISTANCE_MAP.get(distance)
        if distance_km is None:
            raise ValueError(
                f"Unknown distance: {distance}. "
                f"Supported: {', '.join(DISTANCE_MAP.keys())}"
            )

        return VDOTCalculator.predict_race_time(vdot, distance_km)

    def calculate_progress(
        self, goal: dict[str, Any] | None, current_vdot: float
    ) -> dict[str, Any] | None:
        """Calculate gap between predicted and goal time.

        Returns None if goal is None.
        """
        if goal is None:
            return None

        goal_type = goal["goal_type"]
        goal_time_seconds = goal["target_time_seconds"]

        # Resolve distance
        distance_km = DISTANCE_MAP.get(goal_type)
        if distance_km is None:
            return None

        predicted_time_seconds = VDOTCalculator.predict_race_time(
            current_vdot, distance_km
        )

        gap_seconds = predicted_time_seconds - goal_time_seconds

        # Determine status
        if gap_seconds <= 0:
            status = "ahead"
        elif gap_seconds <= 30:
            status = "on_track"
        else:
            status = "behind"

        # Format gap
        if gap_seconds <= 0:
            gap_formatted = f"+{abs(gap_seconds)}秒余裕"
        else:
            gap_formatted = f"-{gap_seconds}秒"

        # Pace gap per km
        pace_gap_per_km = gap_seconds / distance_km
        if gap_seconds > 0:
            pace_gap_formatted = f"あと{pace_gap_per_km:.0f}秒/km改善が必要"
        else:
            pace_gap_formatted = f"{abs(pace_gap_per_km):.0f}秒/km余裕あり"

        # Weeks remaining
        weeks_remaining: int | None = None
        target_race_date = goal.get("target_race_date")
        if target_race_date is not None:
            try:
                race_date = datetime.date.fromisoformat(str(target_race_date))
                today = datetime.date.today()
                days_remaining = (race_date - today).days
                weeks_remaining = max(0, days_remaining // 7)
            except (ValueError, TypeError):
                weeks_remaining = None

        # Goal type Japanese label
        goal_type_ja = GOAL_TYPE_JA.get(goal_type, goal_type)

        return {
            "goal_type": goal_type,
            "goal_type_ja": goal_type_ja,
            "race_distance_km": distance_km,
            "goal_time_seconds": goal_time_seconds,
            "goal_time_formatted": _format_time(goal_time_seconds),
            "predicted_time_seconds": predicted_time_seconds,
            "predicted_time_formatted": _format_time(predicted_time_seconds),
            "gap_seconds": -gap_seconds if gap_seconds > 0 else abs(gap_seconds),
            "gap_formatted": gap_formatted,
            "pace_gap_per_km": pace_gap_per_km,
            "pace_gap_formatted": pace_gap_formatted,
            "current_vdot": current_vdot,
            "weeks_remaining": weeks_remaining,
            "status": status,
        }
