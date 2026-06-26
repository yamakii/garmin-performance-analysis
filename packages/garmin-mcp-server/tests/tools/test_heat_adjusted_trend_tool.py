"""Tests for the ``get_heat_adjusted_trend`` MCP tool (Issue #550).

Covers the ``GarminDBReader.get_heat_adjusted_trend`` delegation wrapper and the
ToolDef registry wiring (schema, dispatch, count). Unit tests mock the inner
``GarminDBReader`` used by ``HeatAdjustmentModel`` so no real DuckDB is touched;
the integration test runs against the real DuckDB when available and skips
gracefully otherwise.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tool_schemas import get_tool_definitions
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import build_mcp_tools, dispatch

_ORIGINAL_DATA_DIR = os.environ.get("GARMIN_DATA_DIR")


# --------------------------------------------------------------------------- #
# GarminDBReader.get_heat_adjusted_trend()
# --------------------------------------------------------------------------- #


def _resolve_real_db_path() -> Path | None:
    """Resolve the real DuckDB path independent of test env isolation."""
    candidates: list[Path] = []
    if _ORIGINAL_DATA_DIR:
        candidates.append(
            Path(_ORIGINAL_DATA_DIR) / "database" / "garmin_performance.duckdb"
        )
    candidates.append(
        Path.home() / "garmin_data" / "data" / "database" / "garmin_performance.duckdb"
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@pytest.mark.integration
def test_reader_get_heat_adjusted_trend_happy() -> None:
    """Real DuckDB running activities → status=ok, beta_heat > 0, valid points."""
    db_path = _resolve_real_db_path()
    if db_path is None:
        pytest.skip("Real DuckDB not available; skipping integration test")

    reader = GarminDBReader(str(db_path))
    rows = reader.execute_read_query(
        "SELECT activity_id FROM activities "
        "WHERE avg_heart_rate IS NOT NULL "
        "AND avg_pace_seconds_per_km IS NOT NULL "
        "AND temp_celsius IS NOT NULL "
        "ORDER BY activity_date"
    )
    activity_ids = [int(r[0]) for r in rows]
    if len(activity_ids) < 10:
        pytest.skip(
            "Fewer than 10 complete running activities in DB; skipping integration"
        )

    result = reader.get_heat_adjusted_trend(
        activity_ids=activity_ids,
        start_date="2000-01-01",
        end_date="2100-01-01",
    )

    assert result["status"] == "ok"
    assert result["coefficients"]["beta_heat"] > 0
    assert len(result["points"]) >= 10
    for point in result["points"]:
        assert "neutral_hr" in point
        assert "heat_cost" in point
        assert point["neutral_hr"] == pytest.approx(
            point["raw_hr"] - point["heat_cost"], abs=1e-6
        )

    # MCP-boundary serialization must succeed.
    json.dumps(result, default=str)


@pytest.mark.unit
def test_reader_get_heat_adjusted_trend_insufficient() -> None:
    """A single activity (< MIN_FIT_ACTIVITIES) → status=insufficient_data."""
    inner_reader = MagicMock()
    base = date(2025, 6, 1)
    inner_reader.get_activity_dates.return_value = {1: base.isoformat()}
    inner_reader.get_bulk_activity_fields.return_value = {
        1: {
            "avg_heart_rate": 150.0,
            "avg_pace_seconds_per_km": 330.0,
            "temp_celsius": 25.0,
        }
    }

    with patch(
        "garmin_mcp.rag.queries.heat_adjustment.GarminDBReader",
        return_value=inner_reader,
    ):
        reader = GarminDBReader(":memory:")
        result = reader.get_heat_adjusted_trend(
            activity_ids=[1],
            start_date="2025-06-01",
            end_date="2025-09-01",
        )

    assert result["status"] == "insufficient_data"
    assert result["n"] == 1
    # Must not raise — graceful degradation.
    json.dumps(result, default=str)


# --------------------------------------------------------------------------- #
# ToolDef / dispatch
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_tool_registered_in_all_defs() -> None:
    """The tool is registered and its required fields exclude ``ref_temp_c``."""
    assert "get_heat_adjusted_trend" in ALL_DEFS_BY_NAME

    tool = next(
        t for t in build_mcp_tools(ALL_DEFS) if t.name == "get_heat_adjusted_trend"
    )
    assert tool.inputSchema["required"] == [
        "start_date",
        "end_date",
        "activity_ids",
    ]
    # ref_temp_c is optional (present as a property but not required).
    assert "ref_temp_c" in tool.inputSchema["properties"]
    assert "ref_temp_c" not in tool.inputSchema["required"]


@pytest.mark.unit
def test_tool_dispatch_calls_reader() -> None:
    """Dispatch routes to ``reader.get_heat_adjusted_trend`` with the args."""
    reader = MagicMock()
    reader.get_heat_adjusted_trend.return_value = {"status": "ok"}

    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_heat_adjusted_trend",
        {
            "start_date": "2025-06-01",
            "end_date": "2025-09-01",
            "activity_ids": [1, 2],
        },
    )

    reader.get_heat_adjusted_trend.assert_called_once_with(
        activity_ids=[1, 2],
        start_date="2025-06-01",
        end_date="2025-09-01",
        ref_temp_c=15.0,
    )
    assert result == {"status": "ok"}


@pytest.mark.unit
def test_tool_schema_parity() -> None:
    """The live MCP surface is 56 (54 domain + 2 server) after #563 + #555."""
    live_names = [t.name for t in get_tool_definitions()]
    assert "get_heat_adjusted_trend" in live_names
    assert len(live_names) == 56
    assert len(live_names) == len(set(live_names)), "duplicate tool names on surface"
    assert len(ALL_DEFS) == 54
