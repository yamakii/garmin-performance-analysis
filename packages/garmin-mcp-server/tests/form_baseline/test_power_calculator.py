"""Tests for power_calculator.calculate_power_efficiency_label."""

import pytest

from garmin_mcp.form_baseline.power_calculator import calculate_power_efficiency_label


@pytest.mark.unit
class TestCalculatePowerEfficiencyLabel:
    """Test the 3-level self-baseline descriptor for power efficiency score."""

    @pytest.mark.parametrize(
        ("z", "expected_label"),
        [
            # z-score bands when rel_rmse is supplied: z>=1 上回る, |z|<1 同等,
            # z<=-1 下回る.
            pytest.param(1.2, "上回る", id="z-pos1.2-above"),
            pytest.param(1.0, "上回る", id="z-1-above-boundary"),
            pytest.param(0.0, "同等", id="z-0-at"),
            pytest.param(-0.9, "同等", id="z-neg0.9-at"),
            pytest.param(-1.2, "下回る", id="z-neg1.2-below"),
            pytest.param(-1.0, "下回る", id="z-neg1-below-boundary"),
        ],
    )
    def test_label_z_bands(self, z: float, expected_label: str) -> None:
        rel_rmse = 0.04
        score = z * rel_rmse
        assert (
            calculate_power_efficiency_label(score, rel_rmse=rel_rmse) == expected_label
        )

    @pytest.mark.parametrize(
        ("score", "expected_label"),
        [
            # Fixed absolute bands used when rel_rmse is not supplied.
            pytest.param(0.04, "上回る", id="fallback-above"),
            pytest.param(0.03, "上回る", id="fallback-above-boundary"),
            pytest.param(-0.01, "同等", id="fallback-at"),
            pytest.param(0.0, "同等", id="fallback-at-zero"),
            pytest.param(-0.05, "下回る", id="fallback-below"),
            pytest.param(-0.03, "下回る", id="fallback-below-boundary"),
        ],
    )
    def test_label_fallback_no_rmse(self, score: float, expected_label: str) -> None:
        assert calculate_power_efficiency_label(score, rel_rmse=None) == expected_label

    def test_today_run_is_doukaku(self) -> None:
        """|z| < 1 (within ±1 RMSE) reads as "同等" (at baseline = good).

        Regression: 2026-07-07 run — a single-run -2.5% residual with a 4% RMSE
        baseline (z=-0.625) must read as "同等", not a weakness.
        """
        assert calculate_power_efficiency_label(-0.025, rel_rmse=0.04) == "同等"
