"""Tests for GoalProgressTracker - race goal progress tracking via VDOT."""

import pytest

from garmin_mcp.reporting.components.goal_progress_tracker import GoalProgressTracker


@pytest.mark.unit
class TestPredictRaceTime:
    """Test VDOT-based race time predictions."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_predict_5k_from_vdot(self) -> None:
        """vdot=48.2 should predict 5K time in 21:30-22:00 range."""
        predicted = self.tracker.predict_race_time(48.2, "5k")
        # 21:30 = 1290s, 22:00 = 1320s
        assert 1290 <= predicted <= 1320

    def test_predict_10k_from_vdot(self) -> None:
        """vdot=48.2 should predict 10K time in 44:30-45:30 range."""
        predicted = self.tracker.predict_race_time(48.2, "10k")
        # 44:30 = 2670s, 45:30 = 2730s
        assert 2670 <= predicted <= 2730

    def test_predict_half_from_vdot(self) -> None:
        """vdot=48.2 should predict Half time in 1:38:xx-1:40:xx range."""
        predicted = self.tracker.predict_race_time(48.2, "half")
        # 1:38:00 = 5880s, 1:40:59 = 6059s
        assert 5880 <= predicted <= 6059

    def test_predict_full_from_vdot(self) -> None:
        """vdot=48.2 should predict Full time in 3:26:xx-3:32:xx range."""
        predicted = self.tracker.predict_race_time(48.2, "full")
        # 3:26:00 = 12360s, 3:32:59 = 12779s
        assert 12360 <= predicted <= 12779


@pytest.mark.unit
class TestCalculateProgress:
    """Test progress calculation between predicted and goal times."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_progress_with_active_plan(self) -> None:
        """goal_time=43:00 (2580s), predicted~43:45 => gap ~ -45s."""
        # Test gap math: set goal 45s faster than predicted time
        predicted = self.tracker.predict_race_time(48.2, "10k")
        goal = {
            "distance": "10k",
            "target_seconds": predicted - 45,  # 45 seconds faster than predicted
            "weeks_remaining": 6,
        }
        result = self.tracker.calculate_progress(goal, 48.2)

        assert result is not None
        assert result["gap_seconds"] == 45  # predicted is 45s slower than goal
        assert result["weeks_remaining"] == 6
        assert result["pace_gap_per_km"] == pytest.approx(4.5, abs=0.5)
        assert "summary_ja" in result

    def test_progress_without_active_plan(self) -> None:
        """plan=None should return None."""
        result = self.tracker.calculate_progress(None, 48.2)
        assert result is None


@pytest.mark.unit
class TestGetGoalFromPlan:
    """Test extracting goal from training plan data."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_get_goal_from_plan(self) -> None:
        """Mock plan with race goal should return correct dict."""
        plan_data = {
            "goal_type": "race",
            "goal_time_seconds": 2580,
            "goal_distance": "10k",
            "weeks_remaining": 6,
        }
        result = self.tracker.get_active_plan_goal(plan_data)

        assert result is not None
        assert result["distance"] == "10k"
        assert result["target_seconds"] == 2580
        assert result["weeks_remaining"] == 6

    def test_get_goal_no_plan(self) -> None:
        """None plan should return None."""
        result = self.tracker.get_active_plan_goal(None)
        assert result is None

    def test_get_goal_fitness_plan(self) -> None:
        """Fitness plan (no race goal) should return None."""
        plan_data = {
            "goal_type": "fitness",
            "goal_time_seconds": None,
            "goal_distance": None,
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None
