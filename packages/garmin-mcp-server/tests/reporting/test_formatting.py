"""Unit tests for formatting utility functions."""

import pytest

from garmin_mcp.reporting.components.formatting import (
    extract_phase_ratings,
    format_pace,
    get_activity_type_display,
    get_training_type_category,
)


@pytest.mark.unit
class TestFormatPace:
    """Test format_pace function."""

    def test_exact_minutes(self):
        """Test pace values that are exact minutes."""
        assert format_pace(240.0) == "4:00/km"
        assert format_pace(360.0) == "6:00/km"
        assert format_pace(300.0) == "5:00/km"

    def test_minutes_with_seconds(self):
        """Test pace values with both minutes and seconds."""
        assert format_pace(270.0) == "4:30/km"
        assert format_pace(405.0) == "6:45/km"
        assert format_pace(242.0) == "4:02/km"
        assert format_pace(330.0) == "5:30/km"

    def test_fast_pace(self):
        """Test fast running paces."""
        assert format_pace(180.0) == "3:00/km"
        assert format_pace(195.0) == "3:15/km"

    def test_slow_pace(self):
        """Test slower running paces."""
        assert format_pace(420.0) == "7:00/km"
        assert format_pace(480.0) == "8:00/km"

    def test_seconds_padding(self):
        """Test that seconds are zero-padded to 2 digits."""
        assert format_pace(241.0) == "4:01/km"
        assert format_pace(245.0) == "4:05/km"
        assert format_pace(249.0) == "4:09/km"


@pytest.mark.unit
class TestGetActivityTypeDisplay:
    """Test get_activity_type_display function."""

    def test_recovery_run(self):
        """Test recovery run mapping."""
        result = get_activity_type_display("recovery")
        assert result["ja"] == "リカバリーラン"
        assert result["en"] == "Recovery Run"
        assert "description" in result

    def test_aerobic_base(self):
        """Test aerobic base mapping."""
        result = get_activity_type_display("aerobic_base")
        assert result["ja"] == "有酸素ベース走"
        assert result["en"] == "Aerobic Base"
        assert "description" in result

    def test_tempo_run(self):
        """Test tempo run mapping."""
        result = get_activity_type_display("tempo")
        assert result["ja"] == "テンポラン"
        assert result["en"] == "Tempo Run"
        assert "description" in result

    def test_lactate_threshold(self):
        """Test lactate threshold mapping."""
        result = get_activity_type_display("lactate_threshold")
        assert result["ja"] == "乳酸閾値トレーニング"
        assert result["en"] == "Lactate Threshold"
        assert "description" in result

    def test_vo2max(self):
        """Test VO2 max mapping."""
        result = get_activity_type_display("vo2max")
        assert result["ja"] == "VO2 Maxトレーニング"
        assert result["en"] == "VO2 Max Training"
        assert "description" in result

    def test_anaerobic_capacity(self):
        """Test anaerobic capacity mapping."""
        result = get_activity_type_display("anaerobic_capacity")
        assert result["ja"] == "無酸素容量トレーニング"
        assert result["en"] == "Anaerobic Capacity"
        assert "description" in result

    def test_speed_training(self):
        """Test speed training mapping."""
        result = get_activity_type_display("speed")
        assert result["ja"] == "スピードトレーニング"
        assert result["en"] == "Speed Training"
        assert "description" in result

    def test_interval_training(self):
        """Test interval training mapping."""
        result = get_activity_type_display("interval_training")
        assert result["ja"] == "インターバルトレーニング"
        assert result["en"] == "Interval Training"
        assert "description" in result

    def test_unknown_type_fallback(self):
        """Test unknown training types return fallback."""
        result = get_activity_type_display("unknown_type")
        assert result["ja"] == "その他のトレーニング"
        assert result["en"] == "Other Training"
        assert result["description"] == "分類不明のトレーニング"

    def test_empty_string_fallback(self):
        """Test empty string returns fallback."""
        result = get_activity_type_display("")
        assert result["ja"] == "その他のトレーニング"
        assert result["en"] == "Other Training"

    def test_result_has_required_keys(self):
        """Test all results have required keys."""
        for training_type in [
            "recovery",
            "aerobic_base",
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
            "unknown",
        ]:
            result = get_activity_type_display(training_type)
            assert "ja" in result
            assert "en" in result
            assert "description" in result


@pytest.mark.unit
class TestGetTrainingTypeCategory:
    """Test get_training_type_category function."""

    def test_interval_sprint_category(self):
        """Test interval/sprint category classification."""
        assert get_training_type_category("vo2max") == "interval_sprint"
        assert get_training_type_category("anaerobic_capacity") == "interval_sprint"
        assert get_training_type_category("speed") == "interval_sprint"
        assert get_training_type_category("interval_training") == "interval_sprint"

    def test_tempo_threshold_category(self):
        """Test tempo/threshold category classification."""
        assert get_training_type_category("tempo") == "tempo_threshold"
        assert get_training_type_category("lactate_threshold") == "tempo_threshold"

    def test_low_moderate_category(self):
        """Test low/moderate category classification."""
        assert get_training_type_category("recovery") == "low_moderate"
        assert get_training_type_category("aerobic_base") == "low_moderate"
        assert get_training_type_category("aerobic_endurance") == "low_moderate"

    def test_unknown_types_default_to_low_moderate(self):
        """Test unknown types default to low_moderate category."""
        assert get_training_type_category("unknown") == "low_moderate"
        assert get_training_type_category("") == "low_moderate"
        assert get_training_type_category("custom_type") == "low_moderate"


@pytest.mark.unit
class TestExtractPhaseRatings:
    """Test extract_phase_ratings function."""

    def test_extract_all_phase_ratings(self):
        """Test extracting ratings from all phases."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "良好なウォームアップです (★★★★☆)",
                "run_evaluation": "素晴らしいメイン走です (★★★★★)",
                "recovery_evaluation": "適切な回復です (★★★☆☆)",
                "cooldown_evaluation": "クールダウンが不足しています (★★☆☆☆)",
            }
        }

        result = extract_phase_ratings(section_analyses)

        assert result["warmup_rating"]["score"] == 4.0
        assert result["warmup_rating"]["stars"] == "★★★★☆"

        assert result["run_rating"]["score"] == 5.0
        assert result["run_rating"]["stars"] == "★★★★★"

        assert result["recovery_rating"]["score"] == 3.0
        assert result["recovery_rating"]["stars"] == "★★★☆☆"

        assert result["cooldown_rating"]["score"] == 2.0
        assert result["cooldown_rating"]["stars"] == "★★☆☆☆"

    def test_extract_with_phase_key(self):
        """Test extracting ratings using 'phase' key instead of 'phase_evaluation'."""
        section_analyses = {
            "phase": {
                "warmup_evaluation": "適切です (★★★★☆)",
                "run_evaluation": "良好です (★★★★★)",
                "recovery_evaluation": "改善の余地あり (★★★☆☆)",
                "cooldown_evaluation": "不十分です (★★☆☆☆)",
            }
        }

        result = extract_phase_ratings(section_analyses)

        assert result["warmup_rating"]["score"] == 4.0
        assert result["run_rating"]["score"] == 5.0
        assert result["recovery_rating"]["score"] == 3.0
        assert result["cooldown_rating"]["score"] == 2.0

    def test_missing_phase_data_returns_zeros(self):
        """Test empty section analyses returns zero ratings."""
        result = extract_phase_ratings({})

        assert result["warmup_rating"]["score"] == 0
        assert result["warmup_rating"]["stars"] == ""
        assert result["run_rating"]["score"] == 0
        assert result["run_rating"]["stars"] == ""
        assert result["recovery_rating"]["score"] == 0
        assert result["recovery_rating"]["stars"] == ""
        assert result["cooldown_rating"]["score"] == 0
        assert result["cooldown_rating"]["stars"] == ""

    def test_missing_individual_evaluations(self):
        """Test missing individual evaluation fields return zeros."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "良好です (★★★★☆)",
                # run_evaluation missing
                "recovery_evaluation": None,  # Explicitly None
                # cooldown_evaluation missing
            }
        }

        result = extract_phase_ratings(section_analyses)

        assert result["warmup_rating"]["score"] == 4.0
        assert result["warmup_rating"]["stars"] == "★★★★☆"

        assert result["run_rating"]["score"] == 0
        assert result["run_rating"]["stars"] == ""

        assert result["recovery_rating"]["score"] == 0
        assert result["recovery_rating"]["stars"] == ""

        assert result["cooldown_rating"]["score"] == 0
        assert result["cooldown_rating"]["stars"] == ""

    def test_text_without_star_pattern_returns_zero(self):
        """Test evaluation text without star pattern returns zero rating."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "良好なウォームアップです",  # No stars
                "run_evaluation": "素晴らしいです (5.0/5.0)",  # Different format
                "recovery_evaluation": "",  # Empty string
                "cooldown_evaluation": "クールダウンあり",
            }
        }

        result = extract_phase_ratings(section_analyses)

        # All should be zero since no star patterns found
        assert result["warmup_rating"]["score"] == 0
        assert result["run_rating"]["score"] == 0
        assert result["recovery_rating"]["score"] == 0
        assert result["cooldown_rating"]["score"] == 0

    def test_one_star_rating(self):
        """Test single star rating."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "改善が必要です (★☆☆☆☆)",
                "run_rating": "",
                "recovery_rating": "",
                "cooldown_rating": "",
            }
        }

        result = extract_phase_ratings(section_analyses)

        assert result["warmup_rating"]["score"] == 1.0
        assert result["warmup_rating"]["stars"] == "★☆☆☆☆"

    def test_five_star_rating(self):
        """Test perfect five star rating."""
        section_analyses = {
            "phase_evaluation": {
                "run_evaluation": "完璧です (★★★★★)",
            }
        }

        result = extract_phase_ratings(section_analyses)

        assert result["run_rating"]["score"] == 5.0
        assert result["run_rating"]["stars"] == "★★★★★"

    def test_multiple_star_patterns_uses_first(self):
        """Test that first star pattern is used when multiple exist."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "前半は良好 (★★★★☆) でしたが後半は (★★☆☆☆)",
            }
        }

        result = extract_phase_ratings(section_analyses)

        # Should use first pattern (★★★★☆)
        assert result["warmup_rating"]["score"] == 4.0
        assert result["warmup_rating"]["stars"] == "★★★★☆"

    def test_result_structure(self):
        """Test the structure of returned result."""
        section_analyses = {
            "phase_evaluation": {
                "warmup_evaluation": "良好 (★★★★☆)",
            }
        }

        result = extract_phase_ratings(section_analyses)

        # Check all required keys exist
        assert "warmup_rating" in result
        assert "run_rating" in result
        assert "recovery_rating" in result
        assert "cooldown_rating" in result

        # Check each rating has required subkeys
        for rating_key in [
            "warmup_rating",
            "run_rating",
            "recovery_rating",
            "cooldown_rating",
        ]:
            assert "score" in result[rating_key]
            assert "stars" in result[rating_key]
            assert isinstance(result[rating_key]["score"], (int, float))
            assert isinstance(result[rating_key]["stars"], str)
