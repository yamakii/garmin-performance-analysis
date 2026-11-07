"""The run report's ``athlete_context`` block (#1522).

What the athlete said about a run (``activity_context``, #1520) travels with the
report, so a loaded commute run is never read as a form change. When no commute
row is stated, the report guesses one at read time from the start time and the
first / last GPS fix -- and never writes the guess back.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import _report, _seed_run

# Thursday: a weekday, so an evening point-to-point run reads as a commute.
_DAY = "2026-10-29"
_ACTIVITY_ID = 9100005221


def _set_start(db_path: Path, activity_id: int, start: str) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE activities SET start_time_local = CAST(? AS TIMESTAMP) "
            "WHERE activity_id = ?",
            [start, activity_id],
        )
    finally:
        conn.close()


def _seed_track(
    db_path: Path,
    activity_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    """Three GPS samples: the start, a midpoint and the end."""
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    conn = duckdb.connect(str(db_path))
    try:
        for seq, (ts, point) in enumerate(((0, start), (900, mid), (1800, end))):
            conn.execute(
                "INSERT INTO time_series_metrics (activity_id, seq_no, "
                "timestamp_s, heart_rate, latitude, longitude) "
                "VALUES (?, ?, ?, 140, ?, ?)",
                [activity_id, seq, ts, point[0], point[1]],
            )
    finally:
        conn.close()


def _seed_context(
    db_path: Path,
    activity_id: int,
    kind: str,
    *,
    value: str | None = None,
    load_kg: float | None = None,
) -> None:
    from garmin_mcp.database.inserters.athlete import insert_activity_context

    insert_activity_context(
        row={
            "activity_id": activity_id,
            "kind": kind,
            "value": value,
            "load_kg": load_kg,
            "source": "athlete_stated",
            "note": None,
            "user_id": "default",
        },
        db_path=str(db_path),
    )


@pytest.mark.integration
def test_run_report_includes_stated_load(reader_db_path: Path) -> None:
    """A stated load and commute travel with the report; no guess is made."""
    _seed_run(reader_db_path, activity_id=_ACTIVITY_ID, activity_date=_DAY)
    _set_start(reader_db_path, _ACTIVITY_ID, f"{_DAY} 18:30:00")
    _seed_context(
        reader_db_path, _ACTIVITY_ID, "load", value="running backpack", load_kg=3.0
    )
    _seed_context(reader_db_path, _ACTIVITY_ID, "commute", value="home from work")

    report = _report(reader_db_path, _ACTIVITY_ID)

    assert report is not None
    context = report["athlete_context"]
    assert context["load_kg"] == 3.0
    assert context["inferred"] is None
    assert {item["kind"] for item in context["items"]} == {"load", "commute"}
    load = next(item for item in context["items"] if item["kind"] == "load")
    assert load == {
        "kind": "load",
        "value": "running backpack",
        "load_kg": 3.0,
        "source": "athlete_stated",
        "note": None,
    }
    json.dumps(report, ensure_ascii=False)


@pytest.mark.integration
def test_run_report_inferred_commute_when_unstated(reader_db_path: Path) -> None:
    """A weekday 18:30 run ending 5 km from its start reads as a commute."""
    _seed_run(reader_db_path, activity_id=_ACTIVITY_ID, activity_date=_DAY)
    _set_start(reader_db_path, _ACTIVITY_ID, f"{_DAY} 18:30:00")
    # 0.045 degrees of latitude is ~5 km.
    _seed_track(reader_db_path, _ACTIVITY_ID, (35.680, 139.760), (35.725, 139.760))

    report = _report(reader_db_path, _ACTIVITY_ID)

    assert report is not None
    assert report["athlete_context"] == {
        "items": [],
        "inferred": {"commute": True},
        "load_kg": None,
    }
    # Read-time only: the guess is never written to activity_context.
    conn = duckdb.connect(str(reader_db_path))
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM activity_context WHERE activity_id = ?",
            [_ACTIVITY_ID],
        ).fetchone()
    finally:
        conn.close()
    assert rows is not None
    assert rows[0] == 0


@pytest.mark.integration
def test_run_report_athlete_context_empty_table_missing(reader_db_path: Path) -> None:
    """A database without the I1 tables still reports, with an empty block."""
    _seed_run(reader_db_path, activity_id=_ACTIVITY_ID, activity_date=_DAY)
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.execute("DROP TABLE activity_context")
        conn.execute("DROP TABLE coaching_rules")
    finally:
        conn.close()

    report = _report(reader_db_path, _ACTIVITY_ID)

    assert report is not None
    context = report["athlete_context"]
    assert context["items"] == []
    assert context["load_kg"] is None
    # No start time / GPS seeded: nothing to read a commute from.
    assert context["inferred"] == {"commute": False}
