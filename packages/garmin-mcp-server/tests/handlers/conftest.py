"""Handler test fixtures.

Shared fixtures for MCP tool dispatch tests using a mock GarminDBReader.

The per-domain handler classes were removed in #340; these tests now exercise
the production dispatch path directly via ``dispatch_tool`` (registry lookup +
``format_json_response(..., default=str)``), which is exactly what
``server._dispatch_tool`` does for non-server tools.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


def dispatch_tool(
    reader: Any, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch a registry tool and wrap the result like the MCP server does.

    Mirrors ``garmin_mcp.server._dispatch_tool`` for non-server tools so the
    tests assert against the exact bytes the live server would emit.
    """
    result = dispatch(ALL_DEFS_BY_NAME, reader, name, arguments)
    return [TextContent(type="text", text=format_json_response(result, default=str))]


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
