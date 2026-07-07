"""Tests for power_calculator.calculate_power_efficiency_rating."""

import pytest

from garmin_mcp.form_baseline.power_calculator import calculate_power_efficiency_rating


@pytest.mark.unit
class TestCalculatePowerEfficiencyRating:
    """Test star rating thresholds for power efficiency score."""

    @pytest.mark.parametrize(
        ("score", "expected_rating"),
        [
            # Fixed absolute bands used when rel_rmse is not supplied.
            pytest.param(0.10, "★★★★★", id="5star-high"),
            pytest.param(0.06, "★★★★★", id="5star-boundary"),
            pytest.param(0.04, "★★★★☆", id="4star-mid"),
            pytest.param(0.03, "★★★★☆", id="4star-boundary"),
            pytest.param(0.00, "★★★☆☆", id="3star-mid"),
            pytest.param(-0.025, "★★★☆☆", id="3star-in-noise"),
            pytest.param(-0.03, "★★☆☆☆", id="2star-boundary"),
            pytest.param(-0.05, "★★☆☆☆", id="2star-mid"),
            pytest.param(-0.06, "★☆☆☆☆", id="1star-boundary"),
            pytest.param(-0.10, "★☆☆☆☆", id="1star-low"),
        ],
    )
    def test_rating_tiers(self, score: float, expected_rating: str) -> None:
        assert calculate_power_efficiency_rating(score) == expected_rating

    def test_within_noise_is_3star(self) -> None:
        """|z| < 1 (within ±1 RMSE) is treated as noise → 3★.

        Regression: 2026-07-07 run — a single-run -2.5% residual with a 4% RMSE
        baseline (z=-0.625) must not be penalized below 3★.
        """
        assert calculate_power_efficiency_rating(-0.025, rel_rmse=0.04) == "★★★☆☆"

    @pytest.mark.parametrize(
        ("z", "expected_rating"),
        [
            pytest.param(-2.5, "★☆☆☆☆", id="z-neg2.5-1star"),
            pytest.param(-1.5, "★★☆☆☆", id="z-neg1.5-2star"),
            pytest.param(0.0, "★★★☆☆", id="z-0-3star"),
            pytest.param(1.5, "★★★★☆", id="z-1.5-4star"),
            pytest.param(2.5, "★★★★★", id="z-2.5-5star"),
        ],
    )
    def test_z_scaled_bands(self, z: float, expected_rating: str) -> None:
        rel_rmse = 0.04
        score = z * rel_rmse
        assert (
            calculate_power_efficiency_rating(score, rel_rmse=rel_rmse)
            == expected_rating
        )

    @pytest.mark.parametrize(
        ("score", "expected_rating"),
        [
            pytest.param(-0.025, "★★★☆☆", id="fallback-3star"),
            pytest.param(0.04, "★★★★☆", id="fallback-4star"),
            pytest.param(-0.07, "★☆☆☆☆", id="fallback-1star"),
        ],
    )
    def test_fallback_when_no_rmse(self, score: float, expected_rating: str) -> None:
        assert (
            calculate_power_efficiency_rating(score, rel_rmse=None) == expected_rating
        )
