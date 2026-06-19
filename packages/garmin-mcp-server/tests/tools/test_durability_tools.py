"""Unit tests for the durability ToolDef registration and dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


@pytest.mark.unit
def test_durability_tool_dispatch() -> None:
    """Both durability tools are registered and route to the reader.

    The handler return values must be JSON-serializable (MCP boundary).
    """
    assert "get_activity_durability" in ALL_DEFS_BY_NAME
    assert "get_durability_trend" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.get_activity_durability.return_value = {
        "activity_id": 5001,
        "activity_date": "2025-09-01",
        "distance_km": 18.0,
        "decoupling_pct": 10.0,
        "pace_fade_pct": 0.0,
    }

    result = dispatch(
        ALL_DEFS_BY_NAME, reader, "get_activity_durability", {"activity_id": 5001}
    )
    reader.get_activity_durability.assert_called_once_with(5001)

    payload = json.loads(json.dumps(result, default=str))
    assert payload["decoupling_pct"] == 10.0
    assert payload["pace_fade_pct"] == 0.0

    # get_durability_trend: default min_distance_km=15.0 forwarded.
    reader.get_durability_trend.return_value = {
        "activities": [],
        "trend": {
            "decoupling_slope_per_day": 0.0,
            "data_points": 0,
            "direction": "insufficient_data",
        },
    }

    dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_durability_trend",
        {"start_date": "2025-09-01", "end_date": "2025-09-30"},
    )
    reader.get_durability_trend.assert_called_once_with(
        "2025-09-01", "2025-09-30", 15.0
    )

    # Explicit min_distance_km is forwarded.
    reader.get_durability_trend.reset_mock()
    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_durability_trend",
        {"start_date": "2025-09-01", "end_date": "2025-09-30", "min_distance_km": 20.0},
    )
    reader.get_durability_trend.assert_called_once_with(
        "2025-09-01", "2025-09-30", 20.0
    )

    payload = json.loads(json.dumps(result, default=str))
    assert payload["trend"]["direction"] == "insufficient_data"
