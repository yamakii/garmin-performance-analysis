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

    # Explicit min_distance_km is forwarded.
    reader.get_durability_trend.return_value = {
        "activities": [],
        "trend": {
            "decoupling_slope_per_day": 0.0,
            "data_points": 0,
            "direction": "insufficient_data",
        },
    }
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


@pytest.mark.unit
def test_get_durability_trend_default_forwards_10km() -> None:
    """Default get_durability_trend call forwards min_distance_km=10.0 (#695)."""
    reader = MagicMock()
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
        "2025-09-01", "2025-09-30", 10.0
    )


@pytest.mark.unit
def test_durability_tool_serializes_form_fields() -> None:
    """Form-fade fields (#368) pass through the tool and stay JSON-serializable."""
    reader = MagicMock()
    reader.get_activity_durability.return_value = {
        "activity_id": 5101,
        "activity_date": "2025-09-03",
        "distance_km": 19.0,
        "decoupling_pct": 6.0,
        "pace_fade_pct": 0.0,
        "gct_fade_pct": 8.0,
        "vo_fade_pct": 5.0,
        "vr_fade_pct": None,  # nullable form metric
    }

    result = dispatch(
        ALL_DEFS_BY_NAME, reader, "get_activity_durability", {"activity_id": 5101}
    )
    payload = json.loads(json.dumps(result, default=str))
    assert payload["gct_fade_pct"] == 8.0
    assert payload["vo_fade_pct"] == 5.0
    assert payload["vr_fade_pct"] is None

    reader.get_durability_trend.return_value = {
        "activities": [],
        "trend": {
            "decoupling_slope_per_day": 0.0,
            "data_points": 0,
            "direction": "insufficient_data",
            "gct_fade_slope_per_day": None,
            "form_direction": "insufficient_data",
        },
    }
    trend_result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_durability_trend",
        {"start_date": "2025-09-01", "end_date": "2025-09-30"},
    )
    trend_payload = json.loads(json.dumps(trend_result, default=str))
    assert trend_payload["trend"]["gct_fade_slope_per_day"] is None
    assert trend_payload["trend"]["form_direction"] == "insufficient_data"


@pytest.mark.unit
def test_get_long_run_progression_gate_dispatch() -> None:
    """The gate tool fuses both reader calls into one JSON-safe verdict (#982)."""
    assert "get_long_run_progression_gate" in ALL_DEFS_BY_NAME

    reader = MagicMock()
    reader.get_activity_durability.return_value = {
        "activity_id": 5301,
        "activity_date": "2026-08-30",
        "distance_km": 19.0,
        "decoupling_pct": 4.0,
        "pace_fade_pct": 2.0,
        "gct_fade_ms": 14.0,
        "cadence_fade_spm": -1.0,
        "temperature_c": 27.0,
    }
    reader.find_reference_long_run.return_value = {
        "activity_id": 5302,
        "activity_date": "2026-08-09",
        "distance_km": 18.0,
        "gct_fade_ms": 3.0,
        "cadence_fade_spm": -1.0,
        "pace_fade_pct": 1.0,
        "temperature_c": 26.0,
        "temp_diff_c": -1.0,
    }

    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_long_run_progression_gate",
        {"activity_id": 5301},
    )
    reader.get_activity_durability.assert_called_once_with(5301)
    reader.find_reference_long_run.assert_called_once_with(5301)

    payload = json.loads(json.dumps(result, default=str))
    assert payload["activity_id"] == 5301
    assert payload["verdict"] == "red"
    assert payload["recommendation"] == "shorten"
    assert payload["reference_activity_id"] == 5302
    assert payload["current"]["gct_fade_ms"] == 14.0
    assert payload["reference"]["activity_id"] == 5302
    assert [t["metric"] for t in payload["triggers"]] == ["gct_fade_ms"]


@pytest.mark.unit
def test_get_long_run_progression_gate_without_reference() -> None:
    """No comparable long run -> the reference block and id are null."""
    reader = MagicMock()
    reader.get_activity_durability.return_value = {
        "activity_id": 5303,
        "gct_fade_ms": 2.0,
        "cadence_fade_spm": -1.0,
        "pace_fade_pct": 1.0,
        "temperature_c": 18.0,
    }
    reader.find_reference_long_run.return_value = None

    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_long_run_progression_gate",
        {"activity_id": 5303},
    )

    payload = json.loads(json.dumps(result, default=str))
    assert payload["reference"] is None
    assert payload["reference_activity_id"] is None
    assert payload["verdict"] == "green"
    assert payload["recommendation"] == "extend"
