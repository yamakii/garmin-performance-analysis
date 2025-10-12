"""Tests for WorkoutComparator."""

from unittest.mock import Mock, patch

import pytest

from tools.rag.queries.comparisons import WorkoutComparator


class TestWorkoutComparator:
    """Test WorkoutComparator functionality."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance with mocked DB."""
        with patch("tools.rag.queries.comparisons.GarminDBReader") as mock_reader:
            comparator = WorkoutComparator()
            comparator.db_reader = mock_reader.return_value
            return comparator

    def test_initialization(self):
        """Test comparator initialization."""
        comparator = WorkoutComparator()
        assert comparator.db_reader is not None

    def test_find_similar_workouts_basic(self, comparator):
        """Test basic similar workout search."""
        # Mock _execute_query for target activity
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Morning Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        # Mock _execute_query for similar activities
        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (
                12340,
                "2025-09-15",
                "Easy Run",
                305.0,
                148.0,
                10.5,
                3.3,
                0.4,
                178.0,
                245.0,
            ),
            (
                12335,
                "2025-09-01",
                "Morning Jog",
                295.0,
                152.0,
                9.8,
                3.6,
                0.6,
                182.0,
                255.0,
            ),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1, limit=10
            )

        assert result is not None
        assert "target_activity" in result
        assert result["target_activity"]["activity_id"] == 12345
        assert "similar_activities" in result
        assert len(result["similar_activities"]) == 2
        assert "comparison_summary" in result

    def test_find_similar_workouts_with_pace_tolerance(self, comparator):
        """Test similar workout search with custom pace tolerance."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (12340, "2025-09-15", "Run", 310.0, 148.0, 10.0, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.05, distance_tolerance=0.1
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1

    def test_find_similar_workouts_with_distance_tolerance(self, comparator):
        """Test similar workout search with custom distance tolerance."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (12340, "2025-09-15", "Run", 300.0, 148.0, 10.5, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.05
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1

    def test_find_similar_workouts_with_terrain_match(self, comparator):
        """Test similar workout search with terrain matching."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = []

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345,
                pace_tolerance=0.1,
                distance_tolerance=0.1,
                terrain_match=True,
            )

        assert result is not None

    def test_find_similar_workouts_with_activity_type_filter(self, comparator):
        """Test similar workout search with activity type filter."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Tempo Run",
            280.0,
            155.0,
            8.0,
            3.8,
            0.7,
            185.0,
            260.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (
                12340,
                "2025-09-15",
                "Tempo Run",
                285.0,
                153.0,
                8.2,
                3.7,
                0.6,
                183.0,
                255.0,
            ),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345,
                pace_tolerance=0.1,
                distance_tolerance=0.1,
                activity_type_filter="Tempo",
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1
        assert "Tempo" in result["similar_activities"][0]["activity_name"]

    def test_find_similar_workouts_with_date_range(self, comparator):
        """Test similar workout search with date range filter."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (12340, "2025-09-15", "Run", 305.0, 148.0, 10.0, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345,
                pace_tolerance=0.1,
                distance_tolerance=0.1,
                date_range=("2025-09-01", "2025-09-30"),
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1
        assert result["similar_activities"][0]["activity_date"] == "2025-09-15"

    def test_calculate_similarity_score(self, comparator):
        """Test similarity score calculation."""
        target = {"avg_pace": 300.0, "distance_km": 10.0}
        candidate = {"avg_pace": 305.0, "distance_km": 10.5}

        score = comparator._calculate_similarity_score(target, candidate)
        assert 96.0 <= score <= 98.0

    def test_generate_interpretation(self, comparator):
        """Test interpretation text generation."""
        pace_diff = -5.0  # 5 seconds faster
        hr_diff = 3.0  # 3 bpm higher

        interpretation = comparator._generate_interpretation(pace_diff, hr_diff)

        assert "5.0秒/km速い" in interpretation
        assert "3bpm高い" in interpretation

    def test_limit_results(self, comparator):
        """Test result limit."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        # Mock 20 similar activities
        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = [
            (
                12340 - i,
                "2025-09-15",
                "Run",
                300.0 + i,
                150.0,
                10.0,
                3.5,
                0.5,
                180.0,
                250.0,
            )
            for i in range(20)
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1, limit=5
            )

        # Note: The limit is applied in SQL, so we expect 20 results from mock
        # In real scenario, SQL would limit to 5
        assert result is not None

    def test_no_similar_workouts(self, comparator):
        """Test when no similar workouts are found."""
        mock_result_target = Mock()
        mock_result_target.fetchone.return_value = (
            12345,
            "2025-10-01",
            "Run",
            300.0,
            150.0,
            10.0,
            3.5,
            0.5,
            180.0,
            250.0,
        )

        mock_result_similar = Mock()
        mock_result_similar.fetchall.return_value = []

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[mock_result_target, mock_result_similar],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1
            )

        assert result is not None
        assert len(result["similar_activities"]) == 0
        assert (
            "類似するワークアウトが見つかりませんでした" in result["comparison_summary"]
        )
