"""Unit + integration tests for the get_weight_economy_coupling ToolDef (#554)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.tool_schemas import get_tool_definitions
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


@pytest.mark.unit
def test_tool_registered_in_all_defs() -> None:
    """The tool is registered under its name in the single-source registry."""
    assert "get_weight_economy_coupling" in ALL_DEFS_BY_NAME


@pytest.mark.unit
def test_tool_dispatch_forwards_params() -> None:
    """Dispatch validates params and forwards weeks + default max_gap_days to the
    reader; the result is JSON-serializable (MCP boundary)."""
    reader = MagicMock()
    reader.get_weight_economy_coupling.return_value = {
        "weeks": 26,
        "n_runs_total": 0,
        "n_matched": 0,
        "weight_spread_kg": 0.0,
        "model": None,
        "series": [],
        "note": "",
        "reason": "insufficient",
    }

    result = dispatch(
        ALL_DEFS_BY_NAME, reader, "get_weight_economy_coupling", {"weeks": 26}
    )
    reader.get_weight_economy_coupling.assert_called_once_with(
        weeks=26, max_gap_days=14
    )

    payload = json.loads(json.dumps(result, default=str))
    assert payload["weeks"] == 26


@pytest.mark.unit
def test_tool_count_doc_sync() -> None:
    """With #563 added too, the registry holds 53 domain + 2 server = 55 live."""
    assert len(ALL_DEFS) == 53
    live_names = [t.name for t in get_tool_definitions()]
    assert len(live_names) == 55
    assert "get_weight_economy_coupling" in live_names


def _seed(db_path: Path) -> None:
    weights = [70.0, 73.0, 71.0, 74.0, 70.5, 72.5, 71.5, 73.5, 70.2]
    vo2 = [50.0, 51.2, 50.5, 52.1, 50.1, 51.5, 50.3, 52.3, 50.4]
    hr = 140
    today = datetime.now()
    conn = duckdb.connect(str(db_path))
    try:
        for i, (weight, v) in enumerate(zip(weights, vo2, strict=True)):
            d = (today - timedelta(weeks=len(weights) - 1 - i)).strftime("%Y-%m-%d")
            ef = 0.030 - 0.0005 * (weight - 70.0)
            aid = 5542000 + i
            conn.execute(
                "INSERT INTO activities "
                "(activity_id, activity_date, avg_speed_ms, avg_heart_rate) "
                "VALUES (?, ?, ?, ?)",
                [aid, d, ef * hr, hr],
            )
            conn.execute(
                "INSERT INTO hr_efficiency (activity_id, training_type) "
                "VALUES (?, ?)",
                [aid, "aerobic_base"],
            )
            conn.execute(
                "INSERT INTO body_composition (measurement_id, date, weight_kg) "
                "VALUES (?, ?, ?)",
                [i + 1, d, weight],
            )
            conn.execute(
                "INSERT INTO vo2_max (activity_id, value, date) VALUES (?, ?, ?)",
                [aid, v, d],
            )
    finally:
        conn.close()


@pytest.mark.integration
def test_e2e_dispatch_through_registry(tmp_path: Path) -> None:
    """End-to-end: real-schema DB -> registry dispatch -> documented structure
    and JSON-serializable payload."""
    db_path = tmp_path / "e2e.duckdb"
    GarminDBWriter(db_path=str(db_path))  # initialize full schema
    _seed(db_path)
    reader = GarminDBReader(db_path=str(db_path))

    result = dispatch(
        ALL_DEFS_BY_NAME, reader, "get_weight_economy_coupling", {"weeks": 52}
    )
    assert isinstance(result, dict)
    assert result["n_matched"] == 9
    assert result["model"] is not None
    assert result["model"]["weight"]["coef"] < 0
    assert result["series"]
    json.dumps(result, default=str)
