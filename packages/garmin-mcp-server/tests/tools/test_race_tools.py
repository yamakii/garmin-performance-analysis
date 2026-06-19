"""Unit tests for the race ToolDef registration and dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


@pytest.mark.unit
def test_get_race_readiness_tool_dispatch() -> None:
    """get_race_readiness is registered and dispatch routes to the reader.

    The handler return value must be JSON-serializable (MCP boundary).
    """
    assert "get_race_readiness" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.get_race_readiness.return_value = {
        "current_vdot": 49.0,
        "predicted_times": {
            "race_5k": 1196,
            "race_10k": 2480,
            "half": 5491,
            "full": 11439,
        },
        "goal": None,
        "progress": None,
    }

    result = dispatch(ALL_DEFS_BY_NAME, reader, "get_race_readiness", {})

    reader.get_race_readiness.assert_called_once_with("default", 8)
    # MCP boundary: result must serialize cleanly to a JSON string.
    payload = json.loads(json.dumps(result, default=str))
    assert payload["current_vdot"] == 49.0
    assert set(payload["predicted_times"]) == {"race_5k", "race_10k", "half", "full"}


@pytest.mark.unit
def test_get_race_readiness_tool_dispatch_with_params() -> None:
    """Explicit user_id / lookback_weeks are forwarded to the reader."""
    reader = MagicMock()
    reader.get_race_readiness.return_value = {"current_vdot": None}

    dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_race_readiness",
        {"user_id": "alice", "lookback_weeks": 12},
    )

    reader.get_race_readiness.assert_called_once_with("alice", 12)
