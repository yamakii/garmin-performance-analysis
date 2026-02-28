"""Tests for GoalProgressTracker - race goal progress tracking."""

import pytest

from garmin_mcp.reporting.components.goal_progress_tracker import GoalProgressTracker


@pytest.mark.unit
class TestPredictRaceTime:
    """Test race time prediction from VDOT."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_predict_5k_from_vdot(self) -> None:
        """vdot=48.2 should predict a reasonable 5K time (~20:30)."""
        result = self.tracker.predict_race_time(48.2, "race_5k")
        # VDOT 48.2 predicts ~1234s (20:34) per Daniels' formula
        assert 1200 <= result <= 1300

    def test_predict_10k_from_vdot(self) -> None:
        """vdot=48.2 should predict a reasonable 10K time (~42:39)."""
        result = self.tracker.predict_race_time(48.2, "race_10k")
        # VDOT 48.2 predicts ~2559s (42:39) per Daniels' formula
        assert 2500 <= result <= 2650

    def test_predict_half_from_vdot(self) -> None:
        """vdot=48.2 should predict a reasonable Half time (~1:34:28)."""
        result = self.tracker.predict_race_time(48.2, "race_half")
        # VDOT 48.2 predicts ~5668s (1:34:28) per Daniels' formula
        assert 5600 <= result <= 5800

    def test_predict_full_from_vdot(self) -> None:
        """vdot=48.2 should predict a reasonable Full time (~3:16:38)."""
        result = self.tracker.predict_race_time(48.2, "race_full")
        # VDOT 48.2 predicts ~11798s (3:16:38) per Daniels' formula
        assert 11700 <= result <= 11900

    def test_predict_short_form_distance(self) -> None:
        """Short form distance strings should also work."""
        result_short = self.tracker.predict_race_time(48.2, "5k")
        result_long = self.tracker.predict_race_time(48.2, "race_5k")
        assert result_short == result_long

    def test_predict_unknown_distance_raises(self) -> None:
        """Unknown distance should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown distance"):
            self.tracker.predict_race_time(48.2, "race_3k")


@pytest.mark.unit
class TestGetActiveGoal:
    """Test goal extraction from plan data."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_get_goal_from_plan(self) -> None:
        """Plan with goal_type='race_10k' and target_time should return goal dict."""
        plan_data = {
            "goal_type": "race_10k",
            "target_time_seconds": 2580,
            "target_race_date": "2026-06-15",
        }
        result = self.tracker.get_active_plan_goal(plan_data)

        assert result is not None
        assert result["goal_type"] == "race_10k"
        assert result["target_time_seconds"] == 2580
        assert result["target_race_date"] == "2026-06-15"

    def test_get_goal_no_plan(self) -> None:
        """None plan data should return None."""
        result = self.tracker.get_active_plan_goal(None)
        assert result is None

    def test_get_goal_fitness_plan(self) -> None:
        """Fitness plan should return None."""
        plan_data = {
            "goal_type": "fitness_improvement",
            "target_time_seconds": 2580,
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None

    def test_get_goal_return_to_run_plan(self) -> None:
        """Return-to-run plan should return None."""
        plan_data = {
            "goal_type": "return_to_run",
            "target_time_seconds": 2580,
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None

    def test_get_goal_no_target_time(self) -> None:
        """Plan without target_time_seconds should return None."""
        plan_data = {
            "goal_type": "race_10k",
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None

    def test_get_goal_empty_goal_type(self) -> None:
        """Plan with empty goal_type should return None."""
        plan_data = {
            "goal_type": "",
            "target_time_seconds": 2580,
        }
        result = self.tracker.get_active_plan_goal(plan_data)
        assert result is None


@pytest.mark.unit
class TestCalculateProgress:
    """Test progress calculation."""

    def setup_method(self) -> None:
        self.tracker = GoalProgressTracker()

    def test_progress_with_active_plan(self) -> None:
        """goal_time=2580 (43:00), predicted=2625 (43:45) -> gap=-45s."""
        goal = {
            "goal_type": "race_10k",
            "target_time_seconds": 2580,
        }
        # Find a VDOT that predicts ~2625s for 10K
        # We'll use a VDOT and check the structure
        result = self.tracker.calculate_progress(goal, current_vdot=46.0)

        assert result is not None
        assert result["goal_type"] == "race_10k"
        assert result["goal_type_ja"] == "10K目標"
        assert result["race_distance_km"] == 10.0
        assert result["goal_time_seconds"] == 2580
        assert result["goal_time_formatted"] == "43:00"
        assert "predicted_time_seconds" in result
        assert "predicted_time_formatted" in result
        assert "gap_seconds" in result
        assert "gap_formatted" in result
        assert "pace_gap_per_km" in result
        assert "pace_gap_formatted" in result
        assert result["current_vdot"] == 46.0
        assert result["status"] in ("ahead", "on_track", "behind")

    def test_progress_without_active_plan(self) -> None:
        """None goal should return None."""
        result = self.tracker.calculate_progress(None, current_vdot=48.2)
        assert result is None

    def test_progress_ahead_of_target(self) -> None:
        """When predicted time is faster than goal, status should be 'ahead'."""
        goal = {
            "goal_type": "race_5k",
            "target_time_seconds": 1500,  # 25:00 - slow target
        }
        # High VDOT should easily beat this
        result = self.tracker.calculate_progress(goal, current_vdot=50.0)

        assert result is not None
        assert result["status"] == "ahead"
        assert "余裕" in result["gap_formatted"]

    def test_progress_behind_target(self) -> None:
        """When predicted time is slower than goal, status should be 'behind'."""
        goal = {
            "goal_type": "race_5k",
            "target_time_seconds": 1000,  # 16:40 - very fast target
        }
        # Moderate VDOT should not beat this
        result = self.tracker.calculate_progress(goal, current_vdot=45.0)

        assert result is not None
        assert result["status"] == "behind"
        assert "改善が必要" in result["pace_gap_formatted"]

    def test_progress_with_race_date(self) -> None:
        """When target_race_date is set, weeks_remaining should be calculated."""
        goal = {
            "goal_type": "race_10k",
            "target_time_seconds": 2700,
            "target_race_date": "2027-06-15",  # Far future
        }
        result = self.tracker.calculate_progress(goal, current_vdot=48.0)

        assert result is not None
        assert result["weeks_remaining"] is not None
        assert result["weeks_remaining"] > 0

    def test_progress_without_race_date(self) -> None:
        """When no target_race_date, weeks_remaining should be None."""
        goal = {
            "goal_type": "race_10k",
            "target_time_seconds": 2700,
        }
        result = self.tracker.calculate_progress(goal, current_vdot=48.0)

        assert result is not None
        assert result["weeks_remaining"] is None

    def test_progress_unknown_goal_type(self) -> None:
        """Unknown goal_type should return None."""
        goal = {
            "goal_type": "race_3k",
            "target_time_seconds": 600,
        }
        result = self.tracker.calculate_progress(goal, current_vdot=48.0)
        assert result is None


@pytest.mark.integration
class TestE2EGoalProgress:
    """End-to-end test with realistic data."""

    def test_e2e_goal_progress_with_real_data(self) -> None:
        """Full workflow: plan -> goal -> predict -> progress."""
        tracker = GoalProgressTracker()

        # Simulate realistic plan data
        plan_data = {
            "goal_type": "race_10k",
            "target_time_seconds": 2700,  # 45:00
            "target_race_date": "2027-06-01",
        }

        # Step 1: Extract goal
        goal = tracker.get_active_plan_goal(plan_data)
        assert goal is not None

        # Step 2: Simulate VO2max -> VDOT conversion
        from garmin_mcp.training_plan.vdot import VDOTCalculator

        vo2max = 49.0
        vdot = VDOTCalculator.vdot_from_vo2max(vo2max)
        assert vdot > 0

        # Step 3: Calculate progress
        progress = tracker.calculate_progress(goal, current_vdot=vdot)
        assert progress is not None

        # Step 4: Verify all expected fields
        expected_fields = [
            "goal_type",
            "goal_type_ja",
            "race_distance_km",
            "goal_time_seconds",
            "goal_time_formatted",
            "predicted_time_seconds",
            "predicted_time_formatted",
            "gap_seconds",
            "gap_formatted",
            "pace_gap_per_km",
            "pace_gap_formatted",
            "current_vdot",
            "weeks_remaining",
            "status",
        ]
        for field in expected_fields:
            assert field in progress, f"Missing field: {field}"

        # Step 5: Verify reasonable values
        assert progress["goal_time_formatted"] == "45:00"
        assert progress["race_distance_km"] == 10.0
        assert progress["current_vdot"] == vdot
        assert progress["weeks_remaining"] is not None
        assert progress["weeks_remaining"] > 0
        assert progress["status"] in ("ahead", "on_track", "behind")
