"""Integration test: ``get_current_standing`` on a fixture DB (Issue #1569)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.inserters.athlete import insert_athlete_profile
from garmin_mcp.database.inserters.plan import insert_training_blocks
from garmin_mcp.database.readers.standing import StandingReader

ON_DATE = "2026-01-01"


@pytest.mark.integration
def test_get_current_standing_tool_shape(reader_db_path: Path) -> None:
    end = date.fromisoformat(ON_DATE)
    rows = [
        [15690000 + i, (end - timedelta(days=i * 2)).isoformat(), km, 3600, pace, 150]
        for i, (km, pace) in enumerate(
            [(10.0, 360.0), (6.0, 400.0), (21.0, 390.0), (3.0, 358.0)]
        )
    ]
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.executemany(
            "INSERT INTO activities (activity_id, activity_date, total_distance_km, "
            "total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    finally:
        conn.close()
    insert_athlete_profile(
        profile={
            "user_id": "default",
            "goals": [
                {
                    "race_name": "Spring 10k",
                    "race_date": "2026-02-12",
                    "priority": "A",
                    "goal_type": "time",
                    "distance_km": 10.0,
                    "target_time_seconds": 3580,
                    "status": "active",
                }
            ],
        },
        db_path=str(reader_db_path),
    )
    insert_training_blocks(
        [
            {
                "phase": "build",
                "title": "build block",
                "start_date": "2025-12-22",
                "end_date": "2026-01-18",
                "long_run_ladder": [
                    {"week_start": "2025-12-29", "target_km": 16.0, "kind": "build"},
                    {"week_start": "2026-01-05", "target_km": 18.0, "kind": "build"},
                ],
            }
        ],
        db_path=str(reader_db_path),
    )

    result = StandingReader(db_path=str(reader_db_path)).get_current_standing(
        on_date=ON_DATE
    )

    for key in (
        "goals",
        "block",
        "remaining_steps",
        "proven",
        "recent_near_goal_pace",
        "missing",
    ):
        assert key in result
    assert result["goals"][0]["goal_pace_sec_per_km"] == pytest.approx(358.0)
    assert result["goals"][0]["weeks_to_race"] == 6
    assert result["block"]["current_step"]["week_start"] == "2025-12-29"
    assert [s["week_start"] for s in result["remaining_steps"]] == ["2026-01-05"]
    assert result["proven"]["longest_run"]["distance_km"] == 21.0
    assert [r["date"] for r in result["recent_near_goal_pace"]] == ["2026-01-01"]
    assert "no active goal" not in result["missing"]
