"""Track progress toward race goals using VDOT predictions."""

from typing import Any


class GoalProgressTracker:
    """Track progress toward race goals using VDOT predictions."""

    def get_active_plan_goal(self, plan_data: dict[str, Any] | None) -> dict[str, Any] | None:
        """Get goal from active training plan."""
        raise NotImplementedError

    def predict_race_time(self, vdot: float, distance: str) -> int:
        """Predict race time from current VDOT. Returns seconds."""
        raise NotImplementedError

    def calculate_progress(self, goal: dict[str, Any] | None, current_vdot: float) -> dict[str, Any] | None:
        """Calculate gap between predicted and goal time."""
        raise NotImplementedError
