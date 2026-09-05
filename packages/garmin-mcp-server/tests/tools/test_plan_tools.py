"""Tests for the training plan ledger tools (dispatch level).

Exercises the registry path (``dispatch(ALL_DEFS_BY_NAME, ...)``) rather than
the handlers directly, so the params models and the ToolDef wiring are covered
alongside the read/write roundtrip.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch

WEEK_START = "2026-09-07"


def _call(reader: MagicMock, name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch a tool by name (``dispatch`` is declared to return ``object``)."""
    return dispatch(ALL_DEFS_BY_NAME, reader, name, arguments)


@pytest.fixture(scope="module")
def _plan_tools_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full schema pre-initialized."""
    db_path = tmp_path_factory.mktemp("plan_tools_template") / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def reader(_plan_tools_template: Path, tmp_path: Path) -> MagicMock:
    """A stand-in GarminDBReader whose db_path points at a fresh schema copy."""
    dest = tmp_path / "plan_tools.duckdb"
    shutil.copy2(str(_plan_tools_template), str(dest))
    mock = MagicMock()
    mock.db_path = dest
    return mock


def _blocks() -> list[dict[str, Any]]:
    return [
        {
            "phase": "build",
            "title": "新潟ラダー (19→28km)",
            "start_date": "2026-08-24",
            "end_date": "2026-09-20",
            "purpose": "脚の耐久性を段階的に伸ばす",
            "quality_sessions_per_week": 1,
            "quality_types": ["threshold_cruise", "strides"],
            "long_run_ladder": [
                {"week_start": "2026-08-31", "target_km": 19.0, "kind": "build"},
                {"week_start": "2026-09-07", "target_km": 25.0, "kind": "build"},
                {"week_start": "2026-09-14", "target_km": 28.0, "kind": "build"},
            ],
            "cutback_rule": {"trigger": "long_run_streak>=3", "long_run_pct": -35},
        }
    ]


@pytest.mark.unit
def test_plan_tools_dispatch_roundtrip(reader: MagicMock) -> None:
    """save_training_blocks then get_training_blocks resolves block + ladder."""
    saved = _call(reader, "save_training_blocks", {"blocks": _blocks()})
    assert saved["status"] == "saved"
    assert saved["count"] == 1

    result = _call(reader, "get_training_blocks", {"on_date": "2026-09-13"})

    assert len(result["blocks"]) == 1
    assert result["active_block"]["title"] == "新潟ラダー (19→28km)"
    assert result["week_start_date"] == WEEK_START
    assert result["ladder_step"]["current"]["target_km"] == 25.0
    assert result["ladder_step"]["previous"]["target_km"] == 19.0
    assert result["ladder_step"]["next"]["target_km"] == 28.0


@pytest.mark.unit
def test_get_weekly_prescriptions_requires_exactly_one_selector(
    reader: MagicMock,
) -> None:
    """Passing both selectors (or neither) is a usage error, not a silent read."""
    both = _call(
        reader,
        "get_weekly_prescriptions",
        {"week_start_date": WEEK_START, "date": "2026-09-13"},
    )
    assert "error" in both
    assert "exactly one" in both["error"]

    neither = _call(reader, "get_weekly_prescriptions", {})
    assert "error" in neither


@pytest.mark.unit
def test_save_and_get_weekly_prescriptions_dispatch(reader: MagicMock) -> None:
    """A saved batch is readable by week and by day through the tools."""
    saved = _call(
        reader,
        "save_weekly_prescriptions",
        {
            "week_start_date": WEEK_START,
            "prescriptions": [
                {
                    "date": "2026-09-13",
                    "session_type": "long",
                    "title": "ロング 25km",
                    "target_km": 25.0,
                    "hr_high": 150,
                },
                {
                    "date": "2026-09-09",
                    "session_type": "easy",
                    "title": "イージー 50分",
                    "target_minutes": 50,
                    "hr_high": 141,
                },
            ],
        },
    )
    assert saved["count"] == 2

    by_week = _call(reader, "get_weekly_prescriptions", {"week_start_date": WEEK_START})
    assert [row["title"] for row in by_week] == ["イージー 50分", "ロング 25km"]

    by_day = _call(reader, "get_weekly_prescriptions", {"date": "2026-09-13"})
    assert len(by_day) == 1
    assert by_day[0]["target_km"] == 25.0

    updated = _call(
        reader,
        "update_prescription_status",
        {
            "prescription_id": saved["prescription_ids"][0],
            "status": "registered",
            "garmin_workout_id": 987,
        },
    )
    assert updated["updated"] is True


@pytest.mark.unit
def test_reconcile_prescriptions_dispatch(reader: MagicMock) -> None:
    """Seeded rows are reconciled through the tool and counted."""
    _call(
        reader,
        "save_weekly_prescriptions",
        {
            "week_start_date": "2026-01-05",
            "prescriptions": [
                {
                    "date": "2026-01-06",
                    "session_type": "easy",
                    "title": "イージー 50分",
                    "target_minutes": 50,
                }
            ],
        },
    )
    with get_write_connection(str(reader.db_path)) as conn:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name, "
            "total_distance_km, total_time_seconds) VALUES "
            "(4242, DATE '2026-01-06', 'easy run', 9.0, 3000)"
        )

    result = _call(
        reader,
        "reconcile_prescriptions",
        {"start_date": "2026-01-05", "end_date": "2026-01-11"},
    )

    assert result["updated"] == 1
    assert result["done"] == 1
