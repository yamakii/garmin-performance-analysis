"""Shared fixtures for form_baseline tests."""

import pytest

from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


@pytest.fixture
def sample_models() -> dict:
    """Create sample trained models for testing."""
    return {
        "gct": GCTPowerModel(
            alpha=5.3,
            d=-0.15,
            rmse=5.0,
            n_samples=100,
            speed_range=(3.0, 5.0),
        ),
        "vo": LinearModel(
            a=10.0, b=-2.0, rmse=0.5, n_samples=100, speed_range=(3.0, 5.0)
        ),
        "vr": LinearModel(
            a=10.0, b=-0.5, rmse=0.3, n_samples=100, speed_range=(3.0, 5.0)
        ),
    }
