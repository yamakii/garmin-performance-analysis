"""Tests for ``PlanReader`` (training block ledger + weekly prescriptions).

Covers block lookup by date, the long-run ladder step with its neighbours, the
latest-batch-wins rule for prescriptions, week resolution via
``athlete_profile.week_start_day``, and the multi-week range read used by the
monthly view.

Uses the module-scoped ``reader_db_path`` fixture (schema pre-initialized via
file copy) to avoid per-test GarminDBWriter DDL overhead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.inserters.plan import (
    insert_training_blocks,
    insert_weekly_prescriptions,
)
from garmin_mcp.database.readers.plan import PlanReader

_LADDER = [
    {"week_start": "2026-08-31", "target_km": 19.0, "kind": "build"},
    {"week_start": "2026-09-07", "target_km": 22.0, "kind": "build"},
    {"week_start": "2026-09-14", "target_km": 25.0, "kind": "build"},
]


def _two_blocks() -> list[dict[str, Any]]:
    return [
        {
            "phase": "build",
            "title": "新潟ラダー (19→25km)",
            "start_date": "2026-08-24",
            "end_date": "2026-09-20",
            "quality_types": ["threshold_cruise"],
            "long_run_ladder": _LADDER,
            "cutback_rule": {"trigger": "long_run_streak>=3", "long_run_pct": -35},
        },
        {
            "phase": "taper",
            "title": "新潟テーパー",
            "start_date": "2026-09-21",
            "end_date": "2026-10-11",
            "long_run_ladder": [{"week_start": "2026-09-21", "target_km": 16.0}],
        },
    ]


def _prescription(on_date: str, session_type: str, title: str) -> dict[str, Any]:
    return {"date": on_date, "session_type": session_type, "title": title}


@pytest.mark.unit
def test_get_block_for_date_returns_covering_block(reader_db_path: Path) -> None:
    """A date inside the first block returns it with JSON columns decoded."""
    db_path = str(reader_db_path)
    insert_training_blocks(_two_blocks(), db_path=db_path)

    block = PlanReader(db_path=db_path).get_block_for_date("2026-09-13")

    assert block is not None
    assert block["title"] == "新潟ラダー (19→25km)"
    assert block["start_date"] == "2026-08-24"
    assert isinstance(block["long_run_ladder"], list)
    assert block["long_run_ladder"][1]["target_km"] == 22.0
    assert block["quality_types"] == ["threshold_cruise"]
    assert block["cutback_rule"]["long_run_pct"] == -35


@pytest.mark.unit
def test_get_ladder_step_for_week_returns_step_with_neighbours(
    reader_db_path: Path,
) -> None:
    """The week's ladder step comes back with its previous / next steps."""
    db_path = str(reader_db_path)
    insert_training_blocks(_two_blocks(), db_path=db_path)

    step = PlanReader(db_path=db_path).get_ladder_step_for_week("2026-09-07")

    assert step is not None
    assert step["current"]["target_km"] == 22.0
    assert step["previous"]["target_km"] == 19.0
    assert step["next"]["target_km"] == 25.0


@pytest.mark.unit
def test_get_ladder_step_for_week_none_when_no_block(reader_db_path: Path) -> None:
    """A week outside every block has no ladder step at all."""
    db_path = str(reader_db_path)
    insert_training_blocks(_two_blocks(), db_path=db_path)

    assert PlanReader(db_path=db_path).get_ladder_step_for_week("2026-11-30") is None


@pytest.mark.unit
def test_get_weekly_prescriptions_returns_latest_batch_only(
    reader_db_path: Path,
) -> None:
    """Re-prescribing a week supersedes the earlier batch."""
    db_path = str(reader_db_path)
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription("2026-09-08", "easy", "旧 easy"),
            _prescription("2026-09-10", "threshold", "旧 threshold"),
            _prescription("2026-09-13", "long", "旧 long"),
        ],
        db_path=db_path,
    )
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription("2026-09-13", "long", "新 long"),
            _prescription("2026-09-09", "easy", "新 easy"),
        ],
        db_path=db_path,
    )

    rows = PlanReader(db_path=db_path).get_weekly_prescriptions("2026-09-07")

    assert [r["title"] for r in rows] == ["新 easy", "新 long"]
    assert [r["date"] for r in rows] == ["2026-09-09", "2026-09-13"]


@pytest.mark.unit
def test_get_prescriptions_for_date_uses_week_start_day(reader_db_path: Path) -> None:
    """Sunday 2026-09-13 maps to the Monday-start week 2026-09-07."""
    db_path = str(reader_db_path)
    with get_write_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO athlete_profile (user_id, week_start_day) "
            "VALUES ('default', 0)"
        )
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription("2026-09-12", "easy", "金 easy"),
            _prescription("2026-09-13", "long", "ロング 25km"),
        ],
        db_path=db_path,
    )

    rows = PlanReader(db_path=db_path).get_prescriptions_for_date("2026-09-13")

    assert len(rows) == 1
    assert rows[0]["title"] == "ロング 25km"
    assert rows[0]["week_start_date"] == "2026-09-07"


@pytest.mark.unit
def test_list_prescriptions_spans_weeks(reader_db_path: Path) -> None:
    """A range read returns latest-batch rows from every overlapping week."""
    db_path = str(reader_db_path)
    insert_weekly_prescriptions(
        "2026-08-31",
        [
            _prescription("2026-08-31", "easy", "前週 月"),
            _prescription("2026-09-06", "long", "前週 ロング"),
        ],
        db_path=db_path,
    )
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription("2026-09-08", "easy", "今週 火"),
            _prescription("2026-09-13", "long", "今週 ロング"),
        ],
        db_path=db_path,
    )

    rows = PlanReader(db_path=db_path).list_prescriptions("2026-09-01", "2026-09-10")

    assert [r["title"] for r in rows] == ["前週 ロング", "今週 火"]
    assert all("2026-09-01" <= r["date"] <= "2026-09-10" for r in rows)
