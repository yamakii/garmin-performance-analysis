"""Shared fixtures for form_baseline tests."""

import pytest

from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


@pytest.fixture
def sample_models() -> dict:
    """Create sample trained models for testing.

    ``rmse`` is load-bearing: the scorer scales deviations by each model's own
    prediction error, so the values below are chosen to give realistic sigmas at
    4:00/km (speed 4.1667 m/s):
    - gct: rmse lives in log-speed space -> 100 * (exp(0.003 / 0.15) - 1) = 2.02%
    - vo: 100 * 0.05 / 1.667 = 3.00%
    - vr: 100 * 0.107 / 7.917 = 1.35%
    """
    return {
        "gct": GCTPowerModel(
            alpha=5.3,
            d=-0.15,
            rmse=0.003,
            n_samples=100,
            speed_range=(3.0, 5.0),
        ),
        "vo": LinearModel(
            a=10.0, b=-2.0, rmse=0.05, n_samples=100, speed_range=(3.0, 5.0)
        ),
        "vr": LinearModel(
            a=10.0, b=-0.5, rmse=0.107, n_samples=100, speed_range=(3.0, 5.0)
        ),
    }
