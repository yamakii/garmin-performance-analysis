"""Tests for GoalProgressTracker - race goal progress tracking using VDOT predictions."""

import pytest
from garmin_mcp.reporting.components.goal_progress_tracker import GoalProgressTracker


@pytest.mark.unit
class TestPredictRaceTime:
    """Test VDOT-based race time prediction."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_predict_5k_from_vdot(self) -> None:
        """vdot=48.2 -> 5K predicted time in '21:30'~'22:00' range."""
        result = self.tracker.predict_race_time(vdot=48.2, distance="5K")
        # Result is in seconds
        assert isinstance(result, int)
        # 21:30 = 1290s, 22:00 = 1320s
        assert 1290 <= result <= 1320, f"5K prediction {result}s out of range"

    def test_predict_10k_from_vdot(self) -> None:
        """vdot=48.2 -> 10K predicted time in '44:30'~'45:30' range."""
        result = self.tracker.predict_race_time(vdot=48.2, distance="10K")
        assert isinstance(result, int)
        # 44:30 = 2670s, 45:30 = 2730s
        assert 2670 <= result <= 2730, f"10K prediction {result}s out of range"

    def test_predict_half_from_vdot(self) -> None:
        """vdot=48.2 -> Half predicted time in '1:38:xx'~'1:40:xx' range."""
        result = self.tracker.predict_race_time(vdot=48.2, distance="half")
        assert isinstance(result, int)
        # 1:38:00 = 5880s, 1:40:59 = 6059s
        assert 5880 <= result <= 6059, f"Half prediction {result}s out of range"

    def test_predict_full_from_vdot(self) -> None:
        """vdot=48.2 -> Full predicted time in '3:26:xx'~'3:32:xx' range."""
        result = self.tracker.predict_race_time(vdot=48.2, distance="full")
        assert isinstance(result, int)
        # 3:26:00 = 12360s, 3:32:59 = 12779s
        assert 12360 <= result <= 12779, f"Full prediction {result}s out of range"


@pytest.mark.unit
class TestCalculateProgress:
    """Test progress calculation between predicted and goal times."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_progress_with_active_plan(self) -> None:
        """goal_time='43:00', predicted='43:45' -> gap=-45s, pace_gap calculated."""
        goal = {
            "goal_type": "race_10k",
            "goal_time_seconds": 2580,  # 43:00
            "distance": "10K",
            "distance_km": 10.0,
        }
        # Use a VDOT that predicts ~43:45 for 10K
        # VDOT ~49.5 gives roughly 43:45 for 10K
        result = self.tracker.calculate_progress(goal=goal, current_vdot=49.5)

        assert "predicted_time_seconds" in result
        assert "goal_time_seconds" in result
        assert result["goal_time_seconds"] == 2580
        assert "gap_seconds" in result
        # Gap should be negative (predicted is slower than goal)
        assert result["gap_seconds"] < 0
        assert "pace_gap_per_km" in result
        assert result["pace_gap_per_km"] < 0  # Need to be faster

    def test_progress_without_active_plan(self) -> None:
        """get_training_plan returns None -> skip result (goal=None)."""
        result = self.tracker.calculate_progress(goal=None, current_vdot=48.2)
        assert result is None


@pytest.mark.unit
class TestGetActivePlanGoal:
    """Test extracting goal from active training plan."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_get_goal_from_plan(self) -> None:
        """Mock plan with goal_type='10K', goal_time='43:00' -> correct dict."""
        plan_data = {
            "plan_id": "test-plan",
            "goal_type": "race_10k",
            "target_time_seconds": 2580,  # 43:00
            "total_weeks": 12,
            "start_date": "2026-01-05",
            "status": "active",
        }
        result = self.tracker.get_active_plan_goal(plan_data)

        assert result is not None
        assert result["goal_type"] == "race_10k"
        assert result["goal_time_seconds"] == 2580
        assert result["distance"] == "10K"
        assert result["distance_km"] == 10.0

    def test_get_goal_no_plan(self) -> None:
        """Plan data is None -> None returned."""
        result = self.tracker.get_active_plan_goal(None)
        assert result is None

    def test_get_goal_fitness_plan(self) -> None:
        """Fitness plan (no race goal) -> None returned."""
        plan_data = {
            "plan_id": "fitness-plan",
            "goal_type": "fitness",
            "target_time_seconds": None,
            "total_weeks": 8,
            "start_date": "2026-01-05",
            "status": "active",
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None


@pytest.mark.integration
class TestE2EGoalProgress:
    """End-to-end test with realistic data."""

    def test_e2e_goal_progress_with_real_data(self) -> None:
        """Integration test: calculate progress with realistic plan + VDOT."""
        tracker = GoalProgressTracker()

        # Simulate a real plan
        plan_data = {
            "plan_id": "race-2026",
            "goal_type": "race_10k",
            "target_time_seconds": 2580,  # 43:00
            "total_weeks": 12,
            "start_date": "2026-01-05",
            "status": "active",
        }

        goal = tracker.get_active_plan_goal(plan_data)
        assert goal is not None

        # Current VDOT from recent VO2 max measurement
        current_vdot = 48.2
        progress = tracker.calculate_progress(goal=goal, current_vdot=current_vdot)

        assert progress is not None
        assert "predicted_time_seconds" in progress
        assert "gap_seconds" in progress
        assert "pace_gap_per_km" in progress
        assert "predicted_time_formatted" in progress
        assert "goal_time_formatted" in progress

        # With VDOT 48.2, 10K prediction should be ~44:50
        # Goal is 43:00, so gap should be roughly -110s
        assert progress["gap_seconds"] < 0
        assert abs(progress["gap_seconds"]) > 60  # At least 1 min gap
