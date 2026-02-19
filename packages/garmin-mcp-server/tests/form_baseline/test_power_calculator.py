"""Tests for power_calculator.calculate_power_efficiency_rating."""

import pytest

from garmin_mcp.form_baseline.power_calculator import calculate_power_efficiency_rating


@pytest.mark.unit
class TestCalculatePowerEfficiencyRating:
    """Test star rating thresholds for power efficiency score."""

    @pytest.mark.parametrize(
        ("score", "expected_rating"),
        [
            pytest.param(0.10, "\u2605\u2605\u2605\u2605\u2605", id="5star-high"),
            pytest.param(0.05, "\u2605\u2605\u2605\u2605\u2605", id="5star-boundary"),
            pytest.param(0.03, "\u2605\u2605\u2605\u2605\u2606", id="4star-mid"),
            pytest.param(0.02, "\u2605\u2605\u2605\u2605\u2606", id="4star-boundary"),
            pytest.param(0.00, "\u2605\u2605\u2605\u2606\u2606", id="3star-mid"),
            pytest.param(-0.02, "\u2605\u2605\u2605\u2606\u2606", id="3star-boundary"),
            pytest.param(-0.03, "\u2605\u2605\u2606\u2606\u2606", id="2star-mid"),
            pytest.param(-0.05, "\u2605\u2605\u2606\u2606\u2606", id="2star-boundary"),
            pytest.param(-0.10, "\u2605\u2606\u2606\u2606\u2606", id="1star-low"),
        ],
    )
    def test_rating_tiers(self, score: float, expected_rating: str) -> None:
        assert calculate_power_efficiency_rating(score) == expected_rating
