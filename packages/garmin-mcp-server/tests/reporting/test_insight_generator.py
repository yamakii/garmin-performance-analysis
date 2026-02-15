"""Unit tests for InsightGenerator class."""

import pytest

from garmin_mcp.reporting.components.insight_generator import InsightGenerator


@pytest.mark.unit
class TestInsightGenerator:
    """Test suite for InsightGenerator."""

    @pytest.fixture
    def generator(self):
        """Create InsightGenerator instance."""
        return InsightGenerator()

    # ========== extract_numeric_change tests ==========

    @pytest.mark.unit
    def test_extract_numeric_change_faster_pace(self, generator):
        """Test extracting numeric change for faster pace (inverts sign)."""
        assert generator.extract_numeric_change("+3秒速い") == -3.0

    @pytest.mark.unit
    def test_extract_numeric_change_negative_hr(self, generator):
        """Test extracting negative HR change."""
        assert generator.extract_numeric_change("-4 bpm") == -4.0

    @pytest.mark.unit
    def test_extract_numeric_change_positive_power(self, generator):
        """Test extracting positive power change."""
        assert generator.extract_numeric_change("+7 W") == 7.0

    @pytest.mark.unit
    def test_extract_numeric_change_decimal(self, generator):
        """Test extracting decimal value."""
        assert generator.extract_numeric_change("+0.03 m") == 0.03

    @pytest.mark.unit
    def test_extract_numeric_change_no_number(self, generator):
        """Test extracting from text with no number."""
        assert generator.extract_numeric_change("no number") == 0.0

    @pytest.mark.unit
    def test_extract_numeric_change_faster_with_negative_sign(self, generator):
        """Test that '速い' inverts sign even with explicit minus."""
        assert generator.extract_numeric_change("-5秒速い") == -5.0

    @pytest.mark.unit
    def test_extract_numeric_change_slower(self, generator):
        """Test slower pace (positive value, no inversion)."""
        assert generator.extract_numeric_change("+10秒遅い") == 10.0

    @pytest.mark.unit
    def test_extract_numeric_change_no_sign(self, generator):
        """Test number without explicit sign."""
        assert generator.extract_numeric_change("3 bpm") == 3.0

    # ========== extract_numeric_value tests ==========

    @pytest.mark.unit
    def test_extract_numeric_value_power(self, generator):
        """Test extracting numeric value from power text."""
        assert generator.extract_numeric_value("230 W") == 230.0

    @pytest.mark.unit
    def test_extract_numeric_value_hr(self, generator):
        """Test extracting numeric value from HR text."""
        assert generator.extract_numeric_value("171 bpm") == 171.0

    @pytest.mark.unit
    def test_extract_numeric_value_no_number(self, generator):
        """Test extracting from text with no number."""
        assert generator.extract_numeric_value("no number") is None

    @pytest.mark.unit
    def test_extract_numeric_value_decimal(self, generator):
        """Test extracting decimal value."""
        assert generator.extract_numeric_value("123.45 units") == 123.45

    @pytest.mark.unit
    def test_extract_numeric_value_only_number(self, generator):
        """Test extracting from text with only number."""
        assert generator.extract_numeric_value("456") == 456.0

    @pytest.mark.unit
    def test_extract_numeric_value_complex_pace(self, generator):
        """Test that complex pace format returns first number."""
        result = generator.extract_numeric_value("6:48/km")
        assert result == 6.0  # Returns first number found

    # ========== generate_workout_insight tests ==========

    @pytest.mark.unit
    def test_generate_workout_insight_no_data(self, generator):
        """Test insight generation with no data."""
        assert (
            generator.generate_workout_insight({}, "aerobic_base")
            == "データ不足のため算出不可"
        )

    @pytest.mark.unit
    def test_generate_workout_insight_no_comparisons_key(self, generator):
        """Test insight generation with missing comparisons key."""
        similar_workouts = {"some_key": "some_value"}
        assert (
            generator.generate_workout_insight(similar_workouts, "aerobic_base")
            == "データ不足のため算出不可"
        )

    @pytest.mark.unit
    def test_generate_workout_insight_aerobic_base_efficiency_improvement(
        self, generator
    ):
        """Test aerobic base insight with efficiency improvement."""
        similar_workouts = {
            "comparisons": [
                {"metric": "平均ペース", "change": "+3秒速い", "average": "300 sec"},
                {"metric": "平均パワー", "change": "-10 W", "average": "200 W"},
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "aerobic_base")
        assert "効率が5.0%向上" in result
        assert "ペース3秒速い" in result
        assert "パワー10W低下" in result

    @pytest.mark.unit
    def test_generate_workout_insight_recovery_efficiency_improvement(self, generator):
        """Test recovery run insight with efficiency improvement."""
        similar_workouts = {
            "comparisons": [
                {"metric": "平均ペース", "change": "+5秒速い", "average": "320 sec"},
                {"metric": "平均パワー", "change": "-15 W", "average": "180 W"},
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "recovery")
        assert "効率が8.3%向上" in result
        assert "ペース5秒速い" in result
        assert "パワー15W低下" in result

    @pytest.mark.unit
    def test_generate_workout_insight_vo2max_improvements(self, generator):
        """Test VO2 max insight with multiple improvements."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "Work平均ペース",
                    "change": "+4秒速い",
                    "average": "270 sec",
                },
                {"metric": "Work平均パワー", "change": "+12 W", "average": "240 W"},
                {
                    "metric": "Work平均ストライド",
                    "change": "+0.05 m",
                    "average": "1.2 m",
                },
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "vo2max")
        assert "Workペース+4秒速" in result
        assert "パワー+12W" in result
        assert "ストライド+5cm向上" in result
        assert "高強度下でもフォーム効率とパワー出力を改善" in result

    @pytest.mark.unit
    def test_generate_workout_insight_interval_training_pace_only(self, generator):
        """Test interval training insight with pace improvement only."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "Work平均ペース",
                    "change": "+6秒速い",
                    "average": "280 sec",
                },
            ]
        }
        result = generator.generate_workout_insight(
            similar_workouts, "interval_training"
        )
        assert "Workペース+6秒速" in result
        assert "高強度下でもフォーム効率とパワー出力を改善" in result

    @pytest.mark.unit
    def test_generate_workout_insight_lactate_threshold_efficiency(self, generator):
        """Test lactate threshold insight with HR efficiency improvement."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "メイン平均ペース",
                    "change": "+0秒速い",
                    "average": "290 sec",
                },
                {"metric": "メイン平均心拍", "change": "-5 bpm", "average": "170 bpm"},
            ]
        }
        result = generator.generate_workout_insight(
            similar_workouts, "lactate_threshold"
        )
        assert "同じペースで心拍5bpm低下" in result
        assert "閾値での効率が2.9%向上" in result

    @pytest.mark.unit
    def test_generate_workout_insight_tempo_efficiency(self, generator):
        """Test tempo run insight with HR efficiency improvement."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "メイン平均ペース",
                    "change": "+1秒速い",
                    "average": "300 sec",
                },
                {"metric": "メイン平均心拍", "change": "-3 bpm", "average": "165 bpm"},
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "tempo")
        assert "同じペースで心拍3bpm低下" in result
        assert "閾値での効率が1.8%向上" in result

    @pytest.mark.unit
    def test_generate_workout_insight_fallback(self, generator):
        """Test fallback message when no specific pattern matches."""
        similar_workouts = {
            "comparisons": [
                {"metric": "平均ペース", "change": "+10秒遅い", "average": "300 sec"},
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "aerobic_base")
        assert result == "複数指標で改善が見られます"

    @pytest.mark.unit
    def test_generate_workout_insight_no_efficiency_improvement(self, generator):
        """Test aerobic base with no efficiency improvement (pace slower or power higher)."""
        similar_workouts = {
            "comparisons": [
                {"metric": "平均ペース", "change": "+3秒遅い", "average": "300 sec"},
                {"metric": "平均パワー", "change": "+10 W", "average": "200 W"},
            ]
        }
        result = generator.generate_workout_insight(similar_workouts, "aerobic_base")
        assert result == "複数指標で改善が見られます"

    @pytest.mark.unit
    def test_generate_workout_insight_threshold_no_hr_improvement(self, generator):
        """Test threshold with no HR improvement."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "メイン平均ペース",
                    "change": "+0秒速い",
                    "average": "290 sec",
                },
                {"metric": "メイン平均心拍", "change": "+2 bpm", "average": "170 bpm"},
            ]
        }
        result = generator.generate_workout_insight(
            similar_workouts, "lactate_threshold"
        )
        assert result == "複数指標で改善が見られます"

    @pytest.mark.unit
    def test_generate_workout_insight_interval_no_improvements(self, generator):
        """Test interval training with no improvements."""
        similar_workouts = {
            "comparisons": [
                {
                    "metric": "Work平均ペース",
                    "change": "+0秒遅い",
                    "average": "270 sec",
                },
                {"metric": "Work平均パワー", "change": "-5 W", "average": "240 W"},
            ]
        }
        result = generator.generate_workout_insight(
            similar_workouts, "interval_training"
        )
        assert result == "複数指標で改善が見られます"

    # ========== generate_reference_info tests ==========

    @pytest.mark.unit
    def test_generate_reference_info_no_data(self, generator):
        """Test reference info generation with no data."""
        assert generator.generate_reference_info(None, None) == ""

    @pytest.mark.unit
    def test_generate_reference_info_vo2_max_only(self, generator):
        """Test reference info with VO2 max only."""
        vo2_max_data = {"precise_value": 52.3, "category": "Superior"}
        result = generator.generate_reference_info(vo2_max_data, None)
        assert result == "> **参考**: VO2 Max 52.3 ml/kg/min（Superior）"

    @pytest.mark.unit
    def test_generate_reference_info_vo2_max_no_category(self, generator):
        """Test reference info with VO2 max without category."""
        vo2_max_data = {"precise_value": 50.0}
        result = generator.generate_reference_info(vo2_max_data, None)
        assert result == "> **参考**: VO2 Max 50.0 ml/kg/min"

    @pytest.mark.unit
    def test_generate_reference_info_vo2_max_na_category(self, generator):
        """Test reference info with VO2 max N/A category."""
        vo2_max_data = {"precise_value": 48.5, "category": "N/A"}
        result = generator.generate_reference_info(vo2_max_data, None)
        assert result == "> **参考**: VO2 Max 48.5 ml/kg/min"

    @pytest.mark.unit
    def test_generate_reference_info_vo2_max_zero_category(self, generator):
        """Test reference info with VO2 max zero category."""
        vo2_max_data = {"precise_value": 51.0, "category": 0}
        result = generator.generate_reference_info(vo2_max_data, None)
        assert result == "> **参考**: VO2 Max 51.0 ml/kg/min"

    @pytest.mark.unit
    def test_generate_reference_info_lactate_threshold_only(self, generator):
        """Test reference info with lactate threshold only."""
        lactate_threshold_data = {"speed_mps": 3.5}  # 3.5 m/s = 4:46/km
        result = generator.generate_reference_info(None, lactate_threshold_data)
        # 1000 / 3.5 = 285.71 sec = 4:45
        assert result == "> **参考**: 閾値ペース 4:45/km"

    @pytest.mark.unit
    def test_generate_reference_info_both_vo2_and_threshold(self, generator):
        """Test reference info with both VO2 max and lactate threshold."""
        vo2_max_data = {"precise_value": 52.0, "category": "Excellent"}
        lactate_threshold_data = {"speed_mps": 4.0}  # 4.0 m/s = 4:10/km
        result = generator.generate_reference_info(vo2_max_data, lactate_threshold_data)
        assert (
            result
            == "> **参考**: VO2 Max 52.0 ml/kg/min（Excellent）、閾値ペース 4:10/km"
        )

    @pytest.mark.unit
    def test_generate_reference_info_with_ftp_interval(self, generator):
        """Test reference info with FTP for interval training."""
        lactate_threshold_data = {
            "speed_mps": 3.8,
            "functional_threshold_power": 230,
        }
        result = generator.generate_reference_info(
            None, lactate_threshold_data, training_type="interval_training"
        )
        # 1000 / 3.8 = 263.16 sec = 4:23
        assert result == "> **参考**: 閾値ペース 4:23/km、FTP 230W"

    @pytest.mark.unit
    def test_generate_reference_info_with_ftp_high_intensity(self, generator):
        """Test reference info with FTP for high intensity training."""
        vo2_max_data = {"precise_value": 54.0, "category": "Superior"}
        lactate_threshold_data = {
            "speed_mps": 4.2,
            "functional_threshold_power": 245,
        }
        result = generator.generate_reference_info(
            vo2_max_data, lactate_threshold_data, training_type="high_intensity"
        )
        # 1000 / 4.2 = 238.10 sec = 3:58
        assert (
            result
            == "> **参考**: VO2 Max 54.0 ml/kg/min（Superior）、閾値ペース 3:58/km、FTP 245W"
        )

    @pytest.mark.unit
    def test_generate_reference_info_no_ftp_for_aerobic(self, generator):
        """Test that FTP is not shown for aerobic_base training."""
        lactate_threshold_data = {
            "speed_mps": 3.5,
            "functional_threshold_power": 220,
        }
        result = generator.generate_reference_info(
            None, lactate_threshold_data, training_type="aerobic_base"
        )
        # FTP should NOT be included
        assert "FTP" not in result
        assert result == "> **参考**: 閾値ペース 4:45/km"

    @pytest.mark.unit
    def test_generate_reference_info_vo2_fallback_to_value(self, generator):
        """Test VO2 max fallback to 'value' field if 'precise_value' missing."""
        vo2_max_data = {"value": 49.0, "category": "Good"}
        result = generator.generate_reference_info(vo2_max_data, None)
        assert result == "> **参考**: VO2 Max 49.0 ml/kg/min（Good）"

    @pytest.mark.unit
    def test_generate_reference_info_threshold_zero_speed(self, generator):
        """Test lactate threshold with zero speed (should skip)."""
        lactate_threshold_data = {"speed_mps": 0}
        result = generator.generate_reference_info(None, lactate_threshold_data)
        assert result == ""

    @pytest.mark.unit
    def test_generate_reference_info_threshold_no_speed(self, generator):
        """Test lactate threshold without speed field."""
        lactate_threshold_data = {"functional_threshold_power": 230}
        result = generator.generate_reference_info(
            None, lactate_threshold_data, training_type="interval_training"
        )
        # No speed, but FTP should still show for interval training
        assert result == "> **参考**: FTP 230W"

    @pytest.mark.unit
    def test_generate_reference_info_pace_formatting(self, generator):
        """Test various pace formatting scenarios."""
        # Test 5:00/km pace
        lactate_threshold_data = {
            "speed_mps": 3.333333
        }  # 1000/3.333333 = 300 sec = 5:00
        result = generator.generate_reference_info(None, lactate_threshold_data)
        assert "5:00/km" in result

        # Test 6:30/km pace
        lactate_threshold_data = {
            "speed_mps": 2.564102
        }  # 1000/2.564102 = 390 sec = 6:30
        result = generator.generate_reference_info(None, lactate_threshold_data)
        assert "6:30/km" in result
