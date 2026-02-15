"""Unit tests for WorkoutComparator class."""

from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.workout_comparator import WorkoutComparator


@pytest.fixture
def mock_db_reader():
    """Create a mock GarminDBReader."""
    return MagicMock(spec=GarminDBReader)


@pytest.fixture
def workout_comparator(mock_db_reader):
    """Create a WorkoutComparator instance with mock db_reader."""
    return WorkoutComparator(db_reader=mock_db_reader)


class TestGetComparisonPace:
    """Tests for get_comparison_pace method."""

    @pytest.mark.unit
    def test_structured_with_run_metrics(self, workout_comparator):
        """Test structured workout with run_metrics returns main_set pace."""
        performance_data = {
            "training_type": "tempo",
            "run_metrics": {"avg_pace_seconds_per_km": 240.5},
            "basic_metrics": {"avg_pace_seconds_per_km": 260.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 240.5
        assert source == "main_set"

    @pytest.mark.unit
    def test_structured_without_run_metrics(self, workout_comparator):
        """Test structured workout without run_metrics falls back to overall pace."""
        performance_data = {
            "training_type": "lactate_threshold",
            "run_metrics": None,
            "basic_metrics": {"avg_pace_seconds_per_km": 260.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 260.0
        assert source == "overall"

    @pytest.mark.unit
    def test_structured_with_run_metrics_but_no_pace(self, workout_comparator):
        """Test structured workout with run_metrics but missing avg_pace."""
        performance_data = {
            "training_type": "vo2max",
            "run_metrics": {"other_metric": 123},
            "basic_metrics": {"avg_pace_seconds_per_km": 260.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 260.0
        assert source == "overall"

    @pytest.mark.unit
    def test_non_structured_type(self, workout_comparator):
        """Test non-structured training type uses overall pace."""
        performance_data = {
            "training_type": "low_intensity",
            "run_metrics": {"avg_pace_seconds_per_km": 240.5},
            "basic_metrics": {"avg_pace_seconds_per_km": 280.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 280.0
        assert source == "overall"

    @pytest.mark.unit
    def test_missing_training_type(self, workout_comparator):
        """Test missing training_type defaults to overall pace."""
        performance_data = {
            "run_metrics": {"avg_pace_seconds_per_km": 240.5},
            "basic_metrics": {"avg_pace_seconds_per_km": 280.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 280.0
        assert source == "overall"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "training_type",
        [
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        ],
    )
    def test_all_structured_types_with_run_metrics(
        self, workout_comparator, training_type
    ):
        """Test all structured types use run_metrics when available."""
        performance_data = {
            "training_type": training_type,
            "run_metrics": {"avg_pace_seconds_per_km": 240.5},
            "basic_metrics": {"avg_pace_seconds_per_km": 260.0},
        }

        pace, source = workout_comparator.get_comparison_pace(performance_data)

        assert pace == 240.5
        assert source == "main_set"


class TestGetEvaluationTargetText:
    """Tests for get_evaluation_target_text method."""

    @pytest.mark.unit
    def test_interval_sprint_category(self, workout_comparator):
        """Test interval_sprint returns Work segment description."""
        result = workout_comparator.get_evaluation_target_text("interval_sprint")

        assert "Workセグメント5本のみ" in result
        assert "インターバル走" in result

    @pytest.mark.unit
    def test_tempo_threshold_category(self, workout_comparator):
        """Test tempo_threshold returns main section description."""
        result = workout_comparator.get_evaluation_target_text("tempo_threshold")

        assert "メイン区間" in result
        assert "Split 3-6" in result
        assert "閾値走" in result

    @pytest.mark.unit
    def test_low_moderate_category(self, workout_comparator):
        """Test low_moderate returns empty string."""
        result = workout_comparator.get_evaluation_target_text("low_moderate")

        assert result == ""

    @pytest.mark.unit
    def test_other_category(self, workout_comparator):
        """Test unknown category returns empty string."""
        result = workout_comparator.get_evaluation_target_text("unknown_category")

        assert result == ""

    @pytest.mark.unit
    def test_empty_string(self, workout_comparator):
        """Test empty string returns empty result."""
        result = workout_comparator.get_evaluation_target_text("")

        assert result == ""


class TestAddAdditionalComparisons:
    """Tests for _add_additional_comparisons method."""

    @pytest.mark.unit
    def test_all_metrics_with_similar_data(self, workout_comparator):
        """Test all metrics when both current and similar have data."""
        comparisons: list[dict[str, str]] = []
        current_additional = (250.0, 120.0, 220.0, 8.5)  # power, stride, GCT, VO
        similar_additional = (240.0, 115.0, 225.0, 9.0)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert len(comparisons) == 4

        # Power
        assert comparisons[0]["metric"] == "平均パワー"
        assert comparisons[0]["current"] == "250 W"
        assert comparisons[0]["average"] == "240 W"
        assert comparisons[0]["change"] == "+10 W"

        # Stride (converted cm to m)
        assert comparisons[1]["metric"] == "平均ストライド"
        assert comparisons[1]["current"] == "1.20 m"
        assert comparisons[1]["average"] == "1.15 m"
        assert comparisons[1]["change"] == "+0.05 m"
        assert comparisons[1]["trend"] == "↗️ 改善"

        # GCT
        assert comparisons[2]["metric"] == "接地時間"
        assert comparisons[2]["current"] == "220 ms"
        assert comparisons[2]["average"] == "225 ms"
        assert comparisons[2]["change"] == "-5 ms"
        assert comparisons[2]["trend"] == "↗️ 改善"

        # VO
        assert comparisons[3]["metric"] == "垂直振幅"
        assert comparisons[3]["current"] == "8.50 cm"
        assert comparisons[3]["average"] == "9.00 cm"
        assert comparisons[3]["change"] == "-0.50 cm"
        assert comparisons[3]["trend"] == "↗️ 改善"

    @pytest.mark.unit
    def test_similar_is_none(self, workout_comparator):
        """Test when similar_additional is None."""
        comparisons: list[dict[str, str]] = []
        current_additional = (250.0, 120.0, 220.0, 8.5)
        similar_additional = None

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert len(comparisons) == 4

        # All should show N/A for average/change/trend
        for comp in comparisons:
            assert comp["average"] == "N/A"
            assert comp["change"] == "N/A"
            assert comp["trend"] == "N/A"

    @pytest.mark.unit
    def test_current_has_none_values(self, workout_comparator):
        """Test when current_additional has some None values."""
        comparisons: list[dict[str, str]] = []
        current_additional = (250.0, None, 220.0, None)  # Power and GCT only
        similar_additional = (240.0, 115.0, 225.0, 9.0)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        # Only power and GCT should be added (metrics with non-None current values)
        assert len(comparisons) == 2
        assert comparisons[0]["metric"] == "平均パワー"
        assert comparisons[1]["metric"] == "接地時間"

    @pytest.mark.unit
    def test_similar_has_none_values(self, workout_comparator):
        """Test when similar_additional has some None values."""
        comparisons: list[dict[str, str]] = []
        current_additional = (250.0, 120.0, 220.0, 8.5)
        similar_additional = (None, None, 225.0, 9.0)  # Only GCT and VO

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert len(comparisons) == 4

        # Power and stride should have N/A (no similar data)
        assert comparisons[0]["average"] == "N/A"  # Power
        assert comparisons[1]["average"] == "N/A"  # Stride

        # GCT and VO should have actual comparisons
        assert comparisons[2]["average"] == "225 ms"  # GCT
        assert comparisons[3]["average"] == "9.00 cm"  # VO

    @pytest.mark.unit
    def test_power_trend_efficiency_improvement(self, workout_comparator):
        """Test power trend shows efficiency improvement when power decreases."""
        comparisons: list[dict[str, str]] = []
        current_additional = (230.0, None, None, None)
        similar_additional = (250.0, None, None, None)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert comparisons[0]["trend"] == "↗️ 効率向上"

    @pytest.mark.unit
    def test_power_trend_stable(self, workout_comparator):
        """Test power trend shows stable when difference is small and positive."""
        comparisons: list[dict[str, str]] = []
        current_additional = (255.0, None, None, None)
        similar_additional = (250.0, None, None, None)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        # power_diff = +5 (not negative, and abs < 10)
        assert comparisons[0]["trend"] == "➡️ 安定"

    @pytest.mark.unit
    def test_power_trend_improvement(self, workout_comparator):
        """Test power trend shows improvement when power increases significantly."""
        comparisons: list[dict[str, str]] = []
        current_additional = (270.0, None, None, None)
        similar_additional = (250.0, None, None, None)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert comparisons[0]["trend"] == "↗️ 改善"

    @pytest.mark.unit
    def test_stride_trend_improvement(self, workout_comparator):
        """Test stride trend shows improvement when stride increases."""
        comparisons: list[dict[str, str]] = []
        current_additional = (None, 125.0, None, None)
        similar_additional = (None, 120.0, None, None)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert comparisons[0]["trend"] == "↗️ 改善"

    @pytest.mark.unit
    def test_stride_trend_maintained(self, workout_comparator):
        """Test stride trend shows maintained when stride doesn't increase."""
        comparisons: list[dict[str, str]] = []
        current_additional = (None, 120.0, None, None)
        similar_additional = (None, 125.0, None, None)

        workout_comparator._add_additional_comparisons(
            comparisons, current_additional, similar_additional
        )

        assert comparisons[0]["trend"] == "➡️ 維持"


class TestAddRecoveryRateComparison:
    """Tests for _add_recovery_rate_comparison method."""

    @pytest.mark.unit
    def test_with_recovery_data(self, workout_comparator, mock_db_reader):
        """Test recovery rate comparison when data is available."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Mock current activity recovery data
        # Returns: (work_hr, recovery_hr)
        mock_db_reader.execute_read_query.side_effect = [
            [(170.0, 136.0)],  # Current: 80% recovery rate
            [(165.0, 132.0)],  # Similar 1: 80% recovery rate
            [(168.0, 134.4)],  # Similar 2: 80% recovery rate
            [(172.0, 137.6)],  # Similar 3: 80% recovery rate
        ]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert len(comparisons) == 1
        assert comparisons[0]["metric"] == "Recovery回復率"
        assert comparisons[0]["current"] == "80%"
        assert comparisons[0]["average"] == "80%"
        assert comparisons[0]["change"] == "+0%"
        assert comparisons[0]["trend"] == "➡️ 維持"

    @pytest.mark.unit
    def test_improved_recovery_rate(self, workout_comparator, mock_db_reader):
        """Test recovery rate comparison showing improvement."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Current has better recovery (85%) vs similar average (80%)
        mock_db_reader.execute_read_query.side_effect = [
            [(170.0, 144.5)],  # Current: 85% recovery rate
            [(165.0, 132.0)],  # Similar 1: 80%
            [(168.0, 134.4)],  # Similar 2: 80%
            [(172.0, 137.6)],  # Similar 3: 80%
        ]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert comparisons[0]["current"] == "85%"
        assert comparisons[0]["average"] == "80%"
        assert comparisons[0]["change"] == "+5%"
        assert comparisons[0]["trend"] == "↗️ 改善"

    @pytest.mark.unit
    def test_degraded_recovery_rate(self, workout_comparator, mock_db_reader):
        """Test recovery rate comparison showing degradation."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Current has worse recovery (75%) vs similar average (80%)
        mock_db_reader.execute_read_query.side_effect = [
            [(170.0, 127.5)],  # Current: 75% recovery rate
            [(165.0, 132.0)],  # Similar 1: 80%
            [(168.0, 134.4)],  # Similar 2: 80%
            [(172.0, 137.6)],  # Similar 3: 80%
        ]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert comparisons[0]["current"] == "75%"
        assert comparisons[0]["average"] == "80%"
        assert comparisons[0]["change"] == "-5%"
        assert comparisons[0]["trend"] == "↘️ 要改善"

    @pytest.mark.unit
    def test_no_similar_recovery_rates(self, workout_comparator, mock_db_reader):
        """Test when no similar activities have recovery data."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Current has data, but similar activities don't
        mock_db_reader.execute_read_query.side_effect = [
            [(170.0, 136.0)],  # Current: 80% recovery rate
            [(None, None)],  # Similar 1: no data
            [(165.0, None)],  # Similar 2: incomplete data
            [(None, 132.0)],  # Similar 3: incomplete data
        ]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert len(comparisons) == 1
        assert comparisons[0]["current"] == "80%"
        assert comparisons[0]["average"] == "N/A"
        assert comparisons[0]["change"] == "N/A"
        assert comparisons[0]["trend"] == "N/A"

    @pytest.mark.unit
    def test_no_current_recovery_data(self, workout_comparator, mock_db_reader):
        """Test when current activity has no recovery data."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Current has no recovery data
        mock_db_reader.execute_read_query.return_value = [(None, None)]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        # No comparison should be added
        assert len(comparisons) == 0

    @pytest.mark.unit
    def test_partial_current_recovery_data(self, workout_comparator, mock_db_reader):
        """Test when current activity has incomplete recovery data."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346, 12347, 12348]

        # Test with only work_hr (no recovery_hr)
        mock_db_reader.execute_read_query.return_value = [(170.0, None)]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert len(comparisons) == 0

        # Test with only recovery_hr (no work_hr)
        comparisons.clear()
        mock_db_reader.execute_read_query.return_value = [(None, 136.0)]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert len(comparisons) == 0

    @pytest.mark.unit
    def test_recovery_rate_calculation(self, workout_comparator, mock_db_reader):
        """Test recovery rate calculation formula."""
        comparisons: list[dict[str, str]] = []
        activity_id = 12345
        similar_ids = [12346]

        # work_hr=180, recovery_hr=90 → 50% recovery rate
        mock_db_reader.execute_read_query.side_effect = [
            [(180.0, 90.0)],  # Current: 50%
            [(180.0, 90.0)],  # Similar: 50%
        ]

        workout_comparator._add_recovery_rate_comparison(
            comparisons, activity_id, similar_ids
        )

        assert comparisons[0]["current"] == "50%"
        assert comparisons[0]["average"] == "50%"
