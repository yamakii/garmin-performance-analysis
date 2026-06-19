"""Unit tests for the training-load (ACWR) ToolDef registration and dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


@pytest.mark.unit
def test_get_acwr_tool_dispatch() -> None:
    """get_acwr is registered and dispatch routes to the reader.

    The handler return value must be JSON-serializable (MCP boundary).
    """
    assert "get_acwr" in ALL_DEFS_BY_NAME
    assert "get_load_trend" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.get_acwr.return_value = {
        "end_date": "2025-10-28",
        "acute_load_7d": 70.0,
        "chronic_load_28d_weekly": 70.0,
        "acwr": 1.0,
        "status": "optimal",
        "load_metric": "distance_km",
    }

    # Default args: end_date omitted -> None forwarded.
    result = dispatch(ALL_DEFS_BY_NAME, reader, "get_acwr", {})
    reader.get_acwr.assert_called_once_with(None)

    payload = json.loads(json.dumps(result, default=str))
    assert payload["acwr"] == 1.0
    assert payload["status"] == "optimal"
    assert payload["load_metric"] == "distance_km"


@pytest.mark.unit
def test_get_acwr_tool_dispatch_with_end_date() -> None:
    """An explicit end_date is forwarded to the reader."""
    reader = MagicMock()
    reader.get_acwr.return_value = {"acwr": None, "status": "insufficient_data"}

    dispatch(ALL_DEFS_BY_NAME, reader, "get_acwr", {"end_date": "2025-10-01"})

    reader.get_acwr.assert_called_once_with("2025-10-01")


@pytest.mark.unit
def test_get_load_trend_tool_dispatch() -> None:
    """get_load_trend forwards lookback_weeks + end_date and is JSON-safe."""
    reader = MagicMock()
    reader.get_load_trend.return_value = {
        "weeks": [
            {
                "week_start": "2025-08-12",
                "load_km": 35.0,
                "acwr": 1.0,
                "status": "optimal",
            }
        ],
        "load_metric": "distance_km",
    }

    # Defaults: lookback_weeks=12, end_date=None.
    dispatch(ALL_DEFS_BY_NAME, reader, "get_load_trend", {})
    reader.get_load_trend.assert_called_once_with(12, None)

    reader.get_load_trend.reset_mock()
    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_load_trend",
        {"lookback_weeks": 8, "end_date": "2025-10-28"},
    )
    reader.get_load_trend.assert_called_once_with(8, "2025-10-28")

    payload = json.loads(json.dumps(result, default=str))
    assert payload["weeks"][0]["status"] == "optimal"
    assert payload["load_metric"] == "distance_km"
