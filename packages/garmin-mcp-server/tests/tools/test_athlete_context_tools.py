"""Unit tests for the activity-context / coaching-rule tools (Issue #1520)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.athlete import SaveActivityContextParams
from garmin_mcp.tools.registry import dispatch

_NEW_TOOLS = {
    "save_activity_context",
    "get_activity_context",
    "save_coaching_rule",
    "get_coaching_rules",
    "deactivate_coaching_rule",
}

_GOLDEN_PATH = (
    Path(__file__).resolve().parents[1] / "snapshots" / "all_tools_golden.json"
)


@pytest.mark.unit
def test_save_activity_context_rejects_load_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SaveActivityContextParams.model_validate(
            {"activity_id": 1, "kind": "load", "load_kg": 50}
        )

    ok = SaveActivityContextParams.model_validate(
        {"activity_id": 1, "kind": "load", "load_kg": 3.0}
    )
    assert ok.load_kg == 3.0
    assert ok.source == "athlete_stated"


@pytest.mark.unit
def test_save_coaching_rule_rejects_pictograph() -> None:
    reader = MagicMock()
    reader.db_path = ":memory:unused"

    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "save_coaching_rule",
        {"scope": "all", "rule_text": "Keep replies calm \U0001f600"},
    )

    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.unit
def test_tools_registered_in_all_defs() -> None:
    names = {d.name for d in ALL_DEFS}
    assert names >= _NEW_TOOLS
    for name in _NEW_TOOLS:
        assert ALL_DEFS_BY_NAME[name].cli_group == "athlete"

    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    golden_names = {entry["name"] for entry in golden}
    assert golden_names >= _NEW_TOOLS
