"""Tests for ActivityClassifier."""

from typing import Any

import pytest

from tools.rag.utils.activity_classifier import ActivityClassifier


@pytest.fixture
def classifier() -> ActivityClassifier:
    """Create an ActivityClassifier instance."""
    return ActivityClassifier()


class TestActivityClassifierBasicClassification:
    """Test basic activity type classification."""

    def test_base_run_classification(self, classifier: ActivityClassifier) -> None:
        """Test Base Run (有酸素ベース) classification."""
        # HR Zone 1-2 is 65% (Zone 1: 30%, Zone 2: 35%)
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 30.0},
                {"zone_number": 2, "zone_percentage": 35.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 10.0},
                {"zone_number": 5, "zone_percentage": 5.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=8.0,
            avg_power=None,
        )

        assert result["type_en"] == "Base Run"
        assert result["type_ja"] == "有酸素ベース走"
        assert "confidence" in result
        assert result["confidence"] == "high"

    def test_threshold_run_classification(self, classifier: ActivityClassifier) -> None:
        """Test Threshold Run (閾値走) classification."""
        # HR Zone 4 is 35%
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 5.0},
                {"zone_number": 2, "zone_percentage": 15.0},
                {"zone_number": 3, "zone_percentage": 30.0},
                {"zone_number": 4, "zone_percentage": 35.0},
                {"zone_number": 5, "zone_percentage": 15.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=10.0,
            avg_power=None,
        )

        assert result["type_en"] == "Threshold Run"
        assert result["type_ja"] == "閾値走"
        assert result["confidence"] == "high"

    def test_sprint_interval_classification(
        self, classifier: ActivityClassifier
    ) -> None:
        """Test Sprint/Interval (スプリント) classification."""
        # HR Zone 5 is 25%
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 10.0},
                {"zone_number": 2, "zone_percentage": 15.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 30.0},
                {"zone_number": 5, "zone_percentage": 25.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=5.0,
            avg_power=None,
        )

        assert result["type_en"] == "Sprint/Interval"
        assert result["type_ja"] == "スプリント/インターバル"
        assert result["confidence"] == "high"

    def test_long_run_classification(self, classifier: ActivityClassifier) -> None:
        """Test Long Run (ロング走) classification."""
        # HR Zone 1-2 is 70% (Zone 1: 35%, Zone 2: 35%) AND distance > 15km
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 35.0},
                {"zone_number": 2, "zone_percentage": 35.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 7.0},
                {"zone_number": 5, "zone_percentage": 3.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=18.0,  # Over 15km
            avg_power=None,
        )

        assert result["type_en"] == "Long Run"
        assert result["type_ja"] == "ロング走"
        assert result["confidence"] == "high"

    def test_recovery_run_classification(self, classifier: ActivityClassifier) -> None:
        """Test Recovery Run (リカバリー) classification."""
        # HR Zone 1 is 75%
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 75.0},
                {"zone_number": 2, "zone_percentage": 15.0},
                {"zone_number": 3, "zone_percentage": 7.0},
                {"zone_number": 4, "zone_percentage": 2.0},
                {"zone_number": 5, "zone_percentage": 1.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=5.0,
            avg_power=None,
        )

        assert result["type_en"] == "Recovery"
        assert result["type_ja"] == "リカバリー走"
        assert result["confidence"] == "high"

    def test_anaerobic_power_classification(
        self, classifier: ActivityClassifier
    ) -> None:
        """Test Anaerobic (無酸素) classification based on power."""
        # Power > 300W
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 10.0},
                {"zone_number": 2, "zone_percentage": 20.0},
                {"zone_number": 3, "zone_percentage": 25.0},
                {"zone_number": 4, "zone_percentage": 25.0},
                {"zone_number": 5, "zone_percentage": 20.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=3.0,
            avg_power=320.0,  # Over 300W
        )

        assert result["type_en"] == "Anaerobic"
        assert result["type_ja"] == "無酸素走"
        assert result["confidence"] == "high"

    def test_anaerobic_hr_classification(self, classifier: ActivityClassifier) -> None:
        """Test Anaerobic classification based on HR Zone 5."""
        # HR Zone 5 is 55%
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 5.0},
                {"zone_number": 2, "zone_percentage": 10.0},
                {"zone_number": 3, "zone_percentage": 15.0},
                {"zone_number": 4, "zone_percentage": 15.0},
                {"zone_number": 5, "zone_percentage": 55.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=2.0,
            avg_power=None,
        )

        assert result["type_en"] == "Anaerobic"
        assert result["type_ja"] == "無酸素走"


class TestActivityClassifierPriorityOrder:
    """Test classification priority order."""

    def test_long_run_priority_over_base(self, classifier: ActivityClassifier) -> None:
        """Test that Long Run has priority over Base Run when distance > 15km."""
        # Meets both Base Run and Long Run criteria
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 35.0},
                {"zone_number": 2, "zone_percentage": 35.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 7.0},
                {"zone_number": 5, "zone_percentage": 3.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=20.0,
            avg_power=None,
        )

        # Should classify as Long Run, not Base Run
        assert result["type_en"] == "Long Run"

    def test_recovery_priority_over_base(self, classifier: ActivityClassifier) -> None:
        """Test that Recovery has priority over Base Run when Zone 1 > 70%."""
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 75.0},
                {"zone_number": 2, "zone_percentage": 15.0},
                {"zone_number": 3, "zone_percentage": 7.0},
                {"zone_number": 4, "zone_percentage": 2.0},
                {"zone_number": 5, "zone_percentage": 1.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=6.0,
            avg_power=None,
        )

        # Should classify as Recovery, not Base Run
        assert result["type_en"] == "Recovery"


class TestActivityClassifierConfidenceLevels:
    """Test confidence level assessment."""

    def test_high_confidence_clear_classification(
        self, classifier: ActivityClassifier
    ) -> None:
        """Test high confidence for clear classification."""
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 80.0},
                {"zone_number": 2, "zone_percentage": 10.0},
                {"zone_number": 3, "zone_percentage": 5.0},
                {"zone_number": 4, "zone_percentage": 3.0},
                {"zone_number": 5, "zone_percentage": 2.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=5.0,
            avg_power=None,
        )

        assert result["confidence"] == "high"

    def test_low_confidence_borderline(self, classifier: ActivityClassifier) -> None:
        """Test low confidence for unclear distributed zones."""
        # Very distributed zones - doesn't match any clear training type
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 20.0},
                {"zone_number": 2, "zone_percentage": 25.0},
                {"zone_number": 3, "zone_percentage": 25.0},
                {"zone_number": 4, "zone_percentage": 20.0},
                {"zone_number": 5, "zone_percentage": 10.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=10.0,
            avg_power=None,
        )

        # Should classify as Unknown with low confidence due to distributed zones
        assert result["type_en"] == "Unknown"
        assert result["confidence"] == "low"


class TestActivityClassifierEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_hr_zones_data(self, classifier: ActivityClassifier) -> None:
        """Test classification with missing HR zones data."""
        result = classifier.classify(
            hr_zones_data=None,
            distance_km=10.0,
            avg_power=None,
        )

        assert result["type_en"] == "Unknown"
        assert result["type_ja"] == "不明"
        assert result["confidence"] == "low"

    def test_empty_zones_list(self, classifier: ActivityClassifier) -> None:
        """Test classification with empty zones list."""
        hr_zones_data: dict[str, list[Any]] = {"zones": []}

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=10.0,
            avg_power=None,
        )

        assert result["type_en"] == "Unknown"

    def test_zero_distance(self, classifier: ActivityClassifier) -> None:
        """Test classification with zero distance."""
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 40.0},
                {"zone_number": 2, "zone_percentage": 40.0},
                {"zone_number": 3, "zone_percentage": 15.0},
                {"zone_number": 4, "zone_percentage": 3.0},
                {"zone_number": 5, "zone_percentage": 2.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=0.0,
            avg_power=None,
        )

        # Should still classify based on HR zones
        assert result["type_en"] == "Base Run"


class TestActivityClassifierKeywordSupport:
    """Test English and Japanese keyword support."""

    def test_english_keywords(self, classifier: ActivityClassifier) -> None:
        """Test that English keywords are correctly returned."""
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 35.0},
                {"zone_number": 2, "zone_percentage": 35.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 7.0},
                {"zone_number": 5, "zone_percentage": 3.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=8.0,
            avg_power=None,
        )

        assert "type_en" in result
        assert isinstance(result["type_en"], str)
        assert len(result["type_en"]) > 0

    def test_japanese_keywords(self, classifier: ActivityClassifier) -> None:
        """Test that Japanese keywords are correctly returned."""
        hr_zones_data = {
            "zones": [
                {"zone_number": 1, "zone_percentage": 35.0},
                {"zone_number": 2, "zone_percentage": 35.0},
                {"zone_number": 3, "zone_percentage": 20.0},
                {"zone_number": 4, "zone_percentage": 7.0},
                {"zone_number": 5, "zone_percentage": 3.0},
            ]
        }

        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=8.0,
            avg_power=None,
        )

        assert "type_ja" in result
        assert isinstance(result["type_ja"], str)
        # Check for Japanese characters (hiragana, katakana, or kanji)
        assert any(
            "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff"
            for char in result["type_ja"]
        )
