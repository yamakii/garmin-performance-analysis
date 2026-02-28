"""Tests for NextRunCalculator - next run pace/HR recommendations."""

import pytest

from garmin_mcp.reporting.components.next_run_calculator import NextRunCalculator


@pytest.mark.unit
class TestCalculateEasyPace:
    """Test easy pace calculation from HR zones and pace-HR history."""

    def setup_method(self) -> None:
        self.calculator = NextRunCalculator()

    def test_easy_pace_from_hr_zones_and_history(self) -> None:
        """Given HR zones and pace-HR history, estimate pace for ~60% Zone 2."""
        hr_zones = {
            "zone_boundaries": [
                {"zone_number": 1, "zone_low_boundary": 97, "zone_high_boundary": 120},
                {"zone_number": 2, "zone_low_boundary": 120, "zone_high_boundary": 141},
                {"zone_number": 3, "zone_low_boundary": 141, "zone_high_boundary": 158},
                {"zone_number": 4, "zone_low_boundary": 158, "zone_high_boundary": 175},
                {"zone_number": 5, "zone_low_boundary": 175, "zone_high_boundary": 197},
            ]
        }
        # pace-HR pairs: (pace_seconds_per_km, avg_hr)
        pace_hr_history = [
            {"pace_seconds_per_km": 390, "avg_hr": 148},  # 6:30/km -> 148bpm
            {"pace_seconds_per_km": 420, "avg_hr": 135},  # 7:00/km -> 135bpm
            {"pace_seconds_per_km": 450, "avg_hr": 125},  # 7:30/km -> 125bpm
            {"pace_seconds_per_km": 360, "avg_hr": 158},  # 6:00/km -> 158bpm
        ]

        result = self.calculator.calculate_easy_pace(hr_zones, pace_hr_history)

        assert result is not None
        # Should recommend HR range within Zone 2
        assert "target_hr_low" in result
        assert "target_hr_high" in result
        assert result["target_hr_low"] >= 120  # Zone 2 low
        assert result["target_hr_high"] <= 141  # Zone 2 high
        # Should include reference pace range
        assert "reference_pace_low" in result
        assert "reference_pace_high" in result
        # Pace should be reasonable (between the history data points)
        assert result["reference_pace_low"] > 0
        assert result["reference_pace_high"] > result["reference_pace_low"]
        # Should include success criterion
        assert "success_criterion" in result
        # Should include adjustment tip
        assert "adjustment_tip" in result

    def test_easy_pace_uses_hr_range_not_pace_target(self) -> None:
        """Easy run recommendations should be HR-based per evaluation-principles.md."""
        hr_zones = {
            "zone_boundaries": [
                {"zone_number": 1, "zone_low_boundary": 97, "zone_high_boundary": 120},
                {"zone_number": 2, "zone_low_boundary": 120, "zone_high_boundary": 141},
                {"zone_number": 3, "zone_low_boundary": 141, "zone_high_boundary": 158},
                {"zone_number": 4, "zone_low_boundary": 158, "zone_high_boundary": 175},
                {"zone_number": 5, "zone_low_boundary": 175, "zone_high_boundary": 197},
            ]
        }
        pace_hr_history = [
            {"pace_seconds_per_km": 420, "avg_hr": 135},
        ]

        result = self.calculator.calculate_easy_pace(hr_zones, pace_hr_history)

        # Primary recommendation is HR, not pace
        assert result["recommendation_type"] == "hr_based"

    def test_easy_pace_insufficient_history(self) -> None:
        """When no pace-HR history is available, return HR range only."""
        hr_zones = {
            "zone_boundaries": [
                {"zone_number": 1, "zone_low_boundary": 97, "zone_high_boundary": 120},
                {"zone_number": 2, "zone_low_boundary": 120, "zone_high_boundary": 141},
                {"zone_number": 3, "zone_low_boundary": 141, "zone_high_boundary": 158},
                {"zone_number": 4, "zone_low_boundary": 158, "zone_high_boundary": 175},
                {"zone_number": 5, "zone_low_boundary": 175, "zone_high_boundary": 197},
            ]
        }

        result = self.calculator.calculate_easy_pace(hr_zones, [])

        assert result is not None
        # Should still provide HR target from Zone 2
        assert "target_hr_low" in result
        assert "target_hr_high" in result
        # No reference pace when history is empty
        assert result.get("reference_pace_low") is None
        assert result.get("reference_pace_high") is None


@pytest.mark.unit
class TestCalculateTempoPace:
    """Test tempo pace calculation from lactate threshold data."""

    def setup_method(self) -> None:
        self.calculator = NextRunCalculator()

    def test_tempo_pace_from_lt_data(self) -> None:
        """Calculate tempo zone from LT pace +/- 5%."""
        lactate_threshold = {
            "speed_mps": 3.175,  # ~5:15/km = 315 sec/km
            "heart_rate": 168,
        }

        result = self.calculator.calculate_tempo_pace(lactate_threshold)

        assert result is not None
        # LT pace = 1000 / 3.175 = ~315 sec/km = 5:15/km
        # Tempo range: LT pace * 0.95 to LT pace * 1.05
        assert "target_pace_low" in result  # faster end
        assert "target_pace_high" in result  # slower end
        assert "target_pace_low_formatted" in result
        assert "target_pace_high_formatted" in result
        # Pace range should bracket LT pace
        lt_pace = 1000 / 3.175
        assert result["target_pace_low"] < lt_pace  # faster
        assert result["target_pace_high"] > lt_pace  # slower
        # Should include HR reference
        assert "target_hr" in result
        assert result["target_hr"] == 168
        assert "success_criterion" in result

    def test_tempo_pace_missing_speed(self) -> None:
        """Graceful degradation when speed data is missing."""
        lactate_threshold = {
            "heart_rate": 168,
        }

        result = self.calculator.calculate_tempo_pace(lactate_threshold)

        assert result is not None
        assert result.get("target_pace_low") is None
        assert "insufficient_data" in result

    def test_tempo_pace_empty_data(self) -> None:
        """Graceful degradation with empty dict."""
        result = self.calculator.calculate_tempo_pace({})

        assert result is not None
        assert "insufficient_data" in result


@pytest.mark.unit
class TestCalculateIntervalPace:
    """Test interval pace calculation from VO2max data."""

    def setup_method(self) -> None:
        self.calculator = NextRunCalculator()

    def test_interval_pace_from_vo2max(self) -> None:
        """Calculate interval pace from VO2max using VDOT-based estimation."""
        vo2_max = {
            "precise_value": 48.5,
        }

        result = self.calculator.calculate_interval_pace(vo2_max)

        assert result is not None
        assert "target_pace_low" in result
        assert "target_pace_high" in result
        assert "target_pace_low_formatted" in result
        assert "target_pace_high_formatted" in result
        # Interval pace should be significantly faster than easy pace
        # For VO2max ~48.5, vVO2max ~13.9 km/h -> ~259 sec/km
        # Interval range is typically 95-100% vVO2max
        assert result["target_pace_low"] > 200  # not unreasonably fast
        assert result["target_pace_high"] < 350  # not unreasonably slow
        assert "success_criterion" in result

    def test_interval_pace_missing_vo2max(self) -> None:
        """Graceful degradation when VO2max is missing."""
        result = self.calculator.calculate_interval_pace({})

        assert result is not None
        assert "insufficient_data" in result

    def test_interval_pace_none_input(self) -> None:
        """Graceful degradation with None input."""
        result = self.calculator.calculate_interval_pace(None)

        assert result is not None
        assert "insufficient_data" in result


@pytest.mark.unit
class TestRecommend:
    """Test the recommend method that selects appropriate recommendation."""

    def setup_method(self) -> None:
        self.calculator = NextRunCalculator()

    def test_recommend_after_easy_run(self) -> None:
        """After an easy run, recommend next easy run with HR target."""
        hr_zones = {
            "zone_boundaries": [
                {"zone_number": 1, "zone_low_boundary": 97, "zone_high_boundary": 120},
                {"zone_number": 2, "zone_low_boundary": 120, "zone_high_boundary": 141},
                {"zone_number": 3, "zone_low_boundary": 141, "zone_high_boundary": 158},
                {"zone_number": 4, "zone_low_boundary": 158, "zone_high_boundary": 175},
                {"zone_number": 5, "zone_low_boundary": 175, "zone_high_boundary": 197},
            ]
        }
        pace_hr_history = [
            {"pace_seconds_per_km": 420, "avg_hr": 135},
        ]

        result = self.calculator.recommend(
            training_type="aerobic_base",
            hr_zones=hr_zones,
            pace_hr_history=pace_hr_history,
        )

        assert result is not None
        assert result["recommended_type"] == "easy"
        assert "target_hr_low" in result
        assert "target_hr_high" in result
        assert "summary_ja" in result  # Japanese summary text

    def test_recommend_after_tempo_run(self) -> None:
        """After a tempo run, recommend next tempo with pace target."""
        lactate_threshold = {
            "speed_mps": 3.175,
            "heart_rate": 168,
        }

        result = self.calculator.recommend(
            training_type="tempo",
            lactate_threshold=lactate_threshold,
        )

        assert result is not None
        assert result["recommended_type"] == "tempo"
        assert "target_pace_low_formatted" in result
        assert "target_pace_high_formatted" in result
        assert "summary_ja" in result

    def test_recommend_after_interval(self) -> None:
        """After interval training, recommend next interval with pace target."""
        vo2_max = {"precise_value": 48.5}

        result = self.calculator.recommend(
            training_type="interval_training",
            vo2_max=vo2_max,
        )

        assert result is not None
        assert result["recommended_type"] == "interval"
        assert "target_pace_low_formatted" in result
        assert "summary_ja" in result

    def test_recommend_graceful_degradation_no_data(self) -> None:
        """When all data is missing, return a meaningful message."""
        result = self.calculator.recommend(
            training_type="aerobic_base",
        )

        assert result is not None
        assert "summary_ja" in result
        # Should have a message about insufficient data
        assert result.get("insufficient_data") is True or "target_hr_low" in result

    def test_recommend_recovery_maps_to_easy(self) -> None:
        """Recovery runs should get easy run recommendations."""
        hr_zones = {
            "zone_boundaries": [
                {"zone_number": 1, "zone_low_boundary": 97, "zone_high_boundary": 120},
                {"zone_number": 2, "zone_low_boundary": 120, "zone_high_boundary": 141},
                {"zone_number": 3, "zone_low_boundary": 141, "zone_high_boundary": 158},
                {"zone_number": 4, "zone_low_boundary": 158, "zone_high_boundary": 175},
                {"zone_number": 5, "zone_low_boundary": 175, "zone_high_boundary": 197},
            ]
        }

        result = self.calculator.recommend(
            training_type="recovery",
            hr_zones=hr_zones,
        )

        assert result is not None
        assert result["recommended_type"] == "easy"

    def test_recommend_lactate_threshold_maps_to_tempo(self) -> None:
        """Lactate threshold runs should get tempo recommendations."""
        lactate_threshold = {
            "speed_mps": 3.175,
            "heart_rate": 168,
        }

        result = self.calculator.recommend(
            training_type="lactate_threshold",
            lactate_threshold=lactate_threshold,
        )

        assert result is not None
        assert result["recommended_type"] == "tempo"
