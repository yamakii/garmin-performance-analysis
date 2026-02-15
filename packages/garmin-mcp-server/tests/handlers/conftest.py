"""Handler test fixtures.

Shared fixtures for MCP handler tests using mock GarminDBReader.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.db_reader import GarminDBReader


@pytest.fixture
def mock_db_reader() -> MagicMock:
    """Create a mock GarminDBReader instance.

    Returns:
        MagicMock spec'd to GarminDBReader.
    """
    return MagicMock(spec=GarminDBReader)


@pytest.fixture
def sample_splits_result() -> dict[str, list[dict]]:
    """Standard splits result for handler tests."""
    return {
        "splits": [
            {
                "split_number": 1,
                "distance_km": 1.0,
                "avg_pace_seconds_per_km": 310,
                "avg_heart_rate": 152,
            },
            {
                "split_number": 2,
                "distance_km": 1.0,
                "avg_pace_seconds_per_km": 315,
                "avg_heart_rate": 155,
            },
        ]
    }


@pytest.fixture
def sample_statistics_result() -> dict[str, Any]:
    """Standard statistics-only result for handler tests."""
    return {
        "activity_id": 12345,
        "statistics_only": True,
        "metrics": {
            "pace": {
                "mean": 312.5,
                "median": 312.5,
                "std": 3.5,
                "min": 310,
                "max": 315,
            },
            "heart_rate": {
                "mean": 153.5,
                "median": 153.5,
                "std": 2.1,
                "min": 152,
                "max": 155,
            },
        },
    }
