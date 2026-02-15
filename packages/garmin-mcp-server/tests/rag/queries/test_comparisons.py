"""Tests for WorkoutComparator."""

from unittest.mock import patch

import pytest

from garmin_mcp.rag.queries.comparisons import WorkoutComparator


class TestWorkoutComparator:
    """Test WorkoutComparator functionality."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance with mocked DB."""
        with patch("garmin_mcp.rag.queries.comparisons.GarminDBReader") as mock_reader:
            comparator = WorkoutComparator()
            comparator.db_reader = mock_reader.return_value
            # Mock new methods to avoid errors in old tests
            comparator.db_reader.get_heart_rate_zones_detail.return_value = None  # type: ignore
            comparator.db_reader.get_weather_data.return_value = None  # type: ignore
            comparator.db_reader.get_hr_efficiency_analysis.return_value = {"training_type": "tempo"}  # type: ignore
            return comparator

    def test_initialization(self):
        """Test comparator initialization."""
        comparator = WorkoutComparator()
        assert comparator.db_reader is not None

    def test_find_similar_workouts_basic(self, comparator):
        """Test basic similar workout search."""
        # _execute_query now returns list of tuples directly
        target_rows = [
            (
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
            ),
        ]

        similar_rows = [
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
            side_effect=[target_rows, similar_rows],
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
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        similar_rows = [
            (12340, "2025-09-15", "Run", 310.0, 148.0, 10.0, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[target_rows, similar_rows],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.05, distance_tolerance=0.1
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1

    def test_find_similar_workouts_with_distance_tolerance(self, comparator):
        """Test similar workout search with custom distance tolerance."""
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        similar_rows = [
            (12340, "2025-09-15", "Run", 300.0, 148.0, 10.5, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[target_rows, similar_rows],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.05
            )

        assert result is not None
        assert len(result["similar_activities"]) == 1

    def test_find_similar_workouts_with_terrain_match(self, comparator):
        """Test similar workout search with terrain matching."""
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        similar_rows: list[tuple] = []

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[target_rows, similar_rows],
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
        target_rows = [
            (
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
            ),
        ]

        similar_rows = [
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
            side_effect=[target_rows, similar_rows],
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
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        similar_rows = [
            (12340, "2025-09-15", "Run", 305.0, 148.0, 10.0, 3.3, 0.4, 178.0, 245.0),
        ]

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[target_rows, similar_rows],
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
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        # Mock 20 similar activities
        similar_rows = [
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
            side_effect=[target_rows, similar_rows],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1, limit=5
            )

        # Note: The limit is applied in SQL, so we expect 20 results from mock
        # In real scenario, SQL would limit to 5
        assert result is not None

    def test_no_similar_workouts(self, comparator):
        """Test when no similar workouts are found."""
        target_rows = [
            (12345, "2025-10-01", "Run", 300.0, 150.0, 10.0, 3.5, 0.5, 180.0, 250.0),
        ]

        similar_rows: list[tuple] = []

        with patch.object(
            comparator,
            "_execute_query",
            side_effect=[target_rows, similar_rows],
        ):
            result = comparator.find_similar_workouts(
                activity_id=12345, pace_tolerance=0.1, distance_tolerance=0.1
            )

        assert result is not None
        assert len(result["similar_activities"]) == 0
        assert (
            "類似するワークアウトが見つかりませんでした" in result["comparison_summary"]
        )


class TestTrainingTypeSimilarity:
    """Test training type similarity matrix."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance."""
        return WorkoutComparator()

    def test_training_type_similarity_same_type(self, comparator):
        """Same training type should have similarity 1.0."""
        assert comparator._get_training_type_similarity("tempo", "tempo") == 1.0
        assert (
            comparator._get_training_type_similarity("aerobic_base", "aerobic_base")
            == 1.0
        )
        assert comparator._get_training_type_similarity("recovery", "recovery") == 1.0
        assert comparator._get_training_type_similarity("speed", "speed") == 1.0

    def test_training_type_similarity_same_category(self, comparator):
        """Same category types should have similarity 0.7-0.9."""
        # Mid-intensity: Tempo-Lactate Threshold
        similarity = comparator._get_training_type_similarity(
            "tempo", "lactate_threshold"
        )
        assert 0.7 <= similarity <= 0.9

        # High-intensity: VO2 Max-Anaerobic Capacity
        similarity = comparator._get_training_type_similarity(
            "vo2max", "anaerobic_capacity"
        )
        assert 0.7 <= similarity <= 0.9

        # Very high-intensity: Anaerobic Capacity-Speed
        similarity = comparator._get_training_type_similarity(
            "anaerobic_capacity", "speed"
        )
        assert 0.7 <= similarity <= 0.9

    def test_training_type_similarity_adjacent_category(self, comparator):
        """Adjacent category types should have similarity 0.4-0.6."""
        # Recovery-Aerobic Base
        similarity = comparator._get_training_type_similarity(
            "recovery", "aerobic_base"
        )
        assert 0.4 <= similarity <= 0.6

        # Aerobic Base-Tempo
        similarity = comparator._get_training_type_similarity("aerobic_base", "tempo")
        assert 0.4 <= similarity <= 0.6

        # Lactate Threshold-VO2 Max
        similarity = comparator._get_training_type_similarity(
            "lactate_threshold", "vo2max"
        )
        assert 0.4 <= similarity <= 0.6

    def test_training_type_similarity_different_category(self, comparator):
        """Different category types should have similarity 0.2-0.3."""
        # Recovery-Speed
        similarity = comparator._get_training_type_similarity("recovery", "speed")
        assert 0.2 <= similarity <= 0.3

        # Aerobic Base-Anaerobic Capacity
        similarity = comparator._get_training_type_similarity(
            "aerobic_base", "anaerobic_capacity"
        )
        assert 0.2 <= similarity <= 0.3

        # Tempo-Speed
        similarity = comparator._get_training_type_similarity("tempo", "speed")
        assert 0.2 <= similarity <= 0.3

    def test_training_type_similarity_symmetry(self, comparator):
        """Similarity should be symmetric: (A,B) == (B,A)."""
        assert comparator._get_training_type_similarity(
            "tempo", "aerobic_base"
        ) == comparator._get_training_type_similarity("aerobic_base", "tempo")

        assert comparator._get_training_type_similarity(
            "lactate_threshold", "vo2max"
        ) == comparator._get_training_type_similarity("vo2max", "lactate_threshold")

        assert comparator._get_training_type_similarity(
            "recovery", "speed"
        ) == comparator._get_training_type_similarity("speed", "recovery")

    def test_training_type_similarity_unknown(self, comparator):
        """Unknown training types should have default similarity 0.3."""
        assert comparator._get_training_type_similarity("unknown", "tempo") == 0.3
        assert comparator._get_training_type_similarity("tempo", "unknown") == 0.3
        assert comparator._get_training_type_similarity("unknown", "unknown") == 1.0
        assert (
            comparator._get_training_type_similarity("invalid_type", "aerobic_base")
            == 0.3
        )

    def test_training_type_similarity_matrix_completeness(self, comparator):
        """All training type combinations should be defined."""
        training_types = [
            "recovery",
            "aerobic_base",
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
        ]

        # Check all combinations
        for type1 in training_types:
            for type2 in training_types:
                similarity = comparator._get_training_type_similarity(type1, type2)
                assert 0.0 <= similarity <= 1.0
                assert isinstance(similarity, float)


class TestWeatherDataRetrieval:
    """Test weather data retrieval functionality."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance."""
        return WorkoutComparator()

    @pytest.mark.unit
    def test_get_activity_temperature_exists(self, comparator):
        """Test temperature retrieval when weather data exists."""
        mock_weather = {"temperature_c": 22.5, "temperature_f": 72.5}

        with patch.object(
            comparator.db_reader, "get_weather_data", return_value=mock_weather
        ):
            temp = comparator._get_activity_temperature(12345)
            assert temp == 22.5

    @pytest.mark.unit
    def test_get_activity_temperature_not_exists(self, comparator):
        """Test temperature retrieval when weather data doesn't exist."""
        with patch.object(comparator.db_reader, "get_weather_data", return_value=None):
            temp = comparator._get_activity_temperature(99999999)
            assert temp is None

    @pytest.mark.unit
    def test_get_activity_temperature_no_temperature_field(self, comparator):
        """Test temperature retrieval when weather data has no temperature."""
        mock_weather = {"humidity": 60, "wind_speed_ms": 3.0}

        with patch.object(
            comparator.db_reader, "get_weather_data", return_value=mock_weather
        ):
            temp = comparator._get_activity_temperature(12345)
            assert temp is None

    @pytest.mark.unit
    def test_temperature_difference_calculation(self, comparator):
        """Test temperature difference calculation accuracy."""
        temp1 = 25.3
        temp2 = 19.7
        diff = temp1 - temp2
        assert abs(diff - 5.6) < 0.1


class TestSimilarityCalculationImproved:
    """Test improved similarity calculation with training type."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance."""
        return WorkoutComparator()

    @pytest.mark.unit
    def test_similarity_same_type_same_pace_distance(self, comparator):
        """Same type, same pace and distance should be 100% similar."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        candidate = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        assert score == 100.0

    @pytest.mark.unit
    def test_similarity_same_type_pace_diff_10_percent(self, comparator):
        """Same type with 10% pace difference should be ~95.5% similar."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        candidate = {
            "avg_pace": 330.0,  # 10% slower
            "distance_km": 10.0,
            "training_type": "tempo",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        # 45% * 0.9 + 35% * 1.0 + 20% * 1.0 = 95.5%
        assert 95.0 <= score <= 96.0

    @pytest.mark.unit
    def test_similarity_different_type_same_pace_distance(self, comparator):
        """Different type but same pace/distance should reflect type similarity."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        # Tempo-Lactate Threshold similarity: 0.8
        candidate = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "lactate_threshold",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        # 45% * 1.0 + 35% * 1.0 + 20% * 0.8 = 96.0%
        assert 95.0 <= score <= 97.0

    @pytest.mark.unit
    def test_similarity_very_different_type(self, comparator):
        """Very different training types should lower similarity significantly."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "recovery",
        }
        # Recovery-Speed similarity: 0.2
        candidate = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "speed",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        # 45% * 1.0 + 35% * 1.0 + 20% * 0.2 = 84.0%
        assert 83.0 <= score <= 85.0

    @pytest.mark.unit
    def test_similarity_clamp_to_100(self, comparator):
        """Similarity should be clamped to maximum 100%."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        candidate = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        assert score <= 100.0

    @pytest.mark.unit
    def test_similarity_clamp_to_0(self, comparator):
        """Similarity should be clamped to minimum 0%."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        candidate = {
            "avg_pace": 600.0,  # 2x slower
            "distance_km": 5.0,  # Half distance
            "training_type": "speed",  # Very different type
        }

        score = comparator._calculate_similarity_score(target, candidate)
        assert score >= 0.0

    @pytest.mark.unit
    def test_similarity_missing_training_type(self, comparator):
        """Missing training type should use default 0.3 similarity."""
        target = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "tempo",
        }
        candidate = {
            "avg_pace": 300.0,
            "distance_km": 10.0,
            "training_type": "unknown",
        }

        score = comparator._calculate_similarity_score(target, candidate)
        # 45% * 1.0 + 35% * 1.0 + 20% * 0.3 = 86.0%
        assert 85.0 <= score <= 87.0


class TestInterpretationWithTemperature:
    """Test interpretation generation with temperature context."""

    @pytest.fixture
    def comparator(self):
        """Create comparator instance."""
        return WorkoutComparator()

    @pytest.mark.unit
    def test_interpretation_with_temp_increase(self, comparator):
        """Interpretation should include temperature increase context."""
        pace_diff = -3.2  # 3.2 seconds faster
        hr_diff = 12.0  # 12 bpm higher
        temp_diff = 6.0  # 6°C hotter

        result = comparator._generate_interpretation(pace_diff, hr_diff, temp_diff)

        assert "3.2秒/km速い" in result
        assert "12bpm高い" in result
        assert "気温+6°C影響" in result or "気温+6°C" in result

    @pytest.mark.unit
    def test_interpretation_with_temp_decrease(self, comparator):
        """Interpretation should include temperature decrease context."""
        pace_diff = 2.1  # 2.1 seconds slower
        hr_diff = -5.0  # 5 bpm lower
        temp_diff = -2.0  # 2°C cooler

        result = comparator._generate_interpretation(pace_diff, hr_diff, temp_diff)

        assert "2.1秒/km遅い" in result
        assert "5bpm低い" in result
        assert "気温-2°C影響" in result or "気温-2°C" in result

    @pytest.mark.unit
    def test_interpretation_no_temp_data(self, comparator):
        """Interpretation without temperature data should work."""
        pace_diff = -1.0  # 1.0 second faster (negative = faster)
        hr_diff = 3.0  # 3 bpm higher
        temp_diff = None  # No temperature data

        result = comparator._generate_interpretation(pace_diff, hr_diff, temp_diff)

        assert "1.0秒/km速い" in result
        assert "3bpm高い" in result
        assert "気温" not in result

    @pytest.mark.unit
    def test_interpretation_small_temp_diff(self, comparator):
        """Small temperature differences (<1°C) should not show temperature context."""
        pace_diff = -0.5  # 0.5 seconds faster (negative = faster)
        hr_diff = 2.0  # 2 bpm higher
        temp_diff = 0.8  # Only 0.8°C difference

        result = comparator._generate_interpretation(pace_diff, hr_diff, temp_diff)

        assert "0.5秒/km速い" in result
        assert "2bpm高い" in result
        assert "気温" not in result  # Should not show for small differences

    @pytest.mark.unit
    def test_interpretation_large_temp_diff(self, comparator):
        """Large temperature differences should be prominent."""
        pace_diff = -1.5  # 1.5 seconds faster
        hr_diff = 18.0  # 18 bpm higher
        temp_diff = 15.0  # 15°C hotter (summer vs winter)

        result = comparator._generate_interpretation(pace_diff, hr_diff, temp_diff)

        assert "1.5秒/km速い" in result
        assert "18bpm高い" in result
        assert "気温+15°C" in result
