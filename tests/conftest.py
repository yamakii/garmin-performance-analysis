"""Pytest configuration and fixtures for test data."""

from pathlib import Path

import pytest


@pytest.fixture
def fixture_base_path() -> Path:
    """Return the base path for test fixtures.

    Returns:
        Path to tests/fixtures directory.
    """
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def dummy_activity_id() -> int:
    """Return the dummy activity ID used in test fixtures.

    Returns:
        Dummy activity ID: 12345678901
    """
    return 12345678901
