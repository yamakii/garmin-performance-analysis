"""Integration tests for ``GarminDBReader.get_post_event_window`` (#1219).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture),
seeds ``athlete_goals`` / ``training_blocks`` / ``activities`` /
``heart_rate_zones`` directly, then asserts the reader's verdict. No real data
or Garmin access.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_activity(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    avg_heart_rate: int | None = None,
    zone3_lower: int | None = None,
) -> None:
    """Insert one activities row (plus its zone-3 row when given)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO activities "
            "(activity_id, activity_date, total_distance_km, avg_heart_rate) "
            "VALUES (?, ?, ?, ?)",
            [activity_id, activity_date, distance_km, avg_heart_rate],
        )
        if zone3_lower is not None:
            conn.execute(
                "INSERT INTO heart_rate_zones "
                "(activity_id, zone_number, zone_low_boundary, zone_high_boundary) "
                "VALUES (?, 3, ?, ?)",
                [activity_id, zone3_lower, zone3_lower + 10],
            )
    finally:
        conn.close()


def _insert_goal(
    db_path: Path,
    *,
    goal_id: int,
    race_date: str,
    race_name: str,
    status: str = "completed",
) -> None:
    """Insert one athlete_goals row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO athlete_goals (goal_id, race_name, race_date, status) "
            "VALUES (?, ?, ?, ?)",
            [goal_id, race_name, race_date, status],
        )
    finally:
        conn.close()


def _insert_block(db_path: Path, *, block_id: int, ladder: list[dict]) -> None:
    """Insert one training_blocks row carrying a long-run ladder."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO training_blocks "
            "(block_id, sequence, phase, title, start_date, end_date, "
            "long_run_ladder) VALUES (?, 1, 'build', 'block', ?, ?, ?)",
            [block_id, "2025-11-01", "2026-01-31", json.dumps(ladder)],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_reader_reads_goals_ladder_and_zones(reader_db_path: Path) -> None:
    """Goal + ladder + zone-joined activities produce the red 2025-12-29 read."""
    _insert_goal(
        reader_db_path, goal_id=1, race_date="2025-12-14", race_name="ハーフマラソン"
    )
    _insert_block(
        reader_db_path,
        block_id=1,
        ladder=[
            {"week_start": "2025-12-08", "target_km": 21.1, "kind": "race"},
            {"week_start": "2025-12-22", "target_km": 24.0, "kind": "extend"},
        ],
    )
    # Pre-event ceiling: the longest run in the 56 days before the race.
    _insert_activity(
        reader_db_path, activity_id=9001, activity_date="2025-11-16", distance_km=21.2
    )
    _insert_activity(
        reader_db_path, activity_id=9002, activity_date="2025-11-30", distance_km=16.0
    )
    # The race itself (141 bpm: below the zone-3 floor, so the proxy misses it).
    _insert_activity(
        reader_db_path,
        activity_id=9003,
        activity_date="2025-12-14",
        distance_km=21.2,
        avg_heart_rate=141,
        zone3_lower=151,
    )
    # 15 days later: +35 % over the ceiling.
    _insert_activity(
        reader_db_path,
        activity_id=9004,
        activity_date="2025-12-29",
        distance_km=28.6,
        avg_heart_rate=145,
        zone3_lower=151,
    )

    reader = GarminDBReader(db_path=str(reader_db_path))
    window = reader.get_post_event_window("2025-12-29")

    assert window["last_event"]["date"] == "2025-12-14"
    assert window["last_event"]["source"] == "goal"
    assert window["days_since_event"] == 15
    assert window["in_window"] is True
    assert window["ceiling_km"] == 21.2
    assert window["longest_since_km"] == 28.6
    assert window["longest_since_activity_id"] == 9004
    assert window["overshoot_pct"] == pytest.approx(34.9, abs=0.05)
    assert window["verdict"] == "red"
    # MCP boundary: the payload must survive json.dumps as-is.
    assert json.loads(json.dumps(window))["verdict"] == "red"


@pytest.mark.integration
def test_reader_default_date_is_latest_activity(reader_db_path: Path) -> None:
    """``date=None`` evaluates the window as of the latest activity_date."""
    _insert_goal(
        reader_db_path, goal_id=2, race_date="2026-02-01", race_name="10km レース"
    )
    _insert_activity(
        reader_db_path, activity_id=9101, activity_date="2026-01-11", distance_km=20.0
    )
    _insert_activity(
        reader_db_path, activity_id=9102, activity_date="2026-02-10", distance_km=18.0
    )

    reader = GarminDBReader(db_path=str(reader_db_path))
    window = reader.get_post_event_window()

    assert window["date"] == "2026-02-10"
    assert window["days_since_event"] == 9
    assert window["in_window"] is True
    assert window["ceiling_km"] == 20.0
    assert window["longest_since_km"] == 18.0
    assert window["verdict"] == "green"
