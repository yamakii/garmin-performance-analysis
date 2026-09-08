"""Tests for ``reconcile_prescriptions`` (prescription → activity linking).

The reconciler is deterministic, so every case is expressed as "seed a
prescription (+ maybe an activity), run with a fixed ``today``, assert the
resulting status".
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.analysis.prescription_reconcile import reconcile_prescriptions
from garmin_mcp.database.connection import get_connection, get_write_connection
from garmin_mcp.database.inserters.plan import insert_weekly_prescriptions
from tests.support.schema import init_schema

TODAY = date(2026, 9, 12)
WEEK_START = "2026-09-07"


@pytest.fixture(scope="module")
def _plan_schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full schema pre-initialized."""
    db_path = tmp_path_factory.mktemp("plan_reconcile_template") / "template.duckdb"
    init_schema(db_path)
    return Path(db_path)


@pytest.fixture
def db_path(_plan_schema_template: Path, tmp_path: Path) -> str:
    """Function-scoped copy of the schema template."""
    dest = tmp_path / "reconcile.duckdb"
    shutil.copy2(str(_plan_schema_template), str(dest))
    return str(dest)


def _prescription(on_date: str, session_type: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": on_date,
        "session_type": session_type,
        "title": f"{session_type} {on_date}",
    }
    row.update(overrides)
    return row


def _add_activity(
    db_path: str, activity_id: int, on_date: str, distance_km: float, minutes: float
) -> None:
    with get_write_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name, "
            "total_distance_km, total_time_seconds) VALUES (?, CAST(? AS DATE), "
            "?, ?, ?)",
            [activity_id, on_date, f"run {on_date}", distance_km, int(minutes * 60)],
        )


def _statuses(db_path: str) -> dict[str, tuple[str, int | None]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT title, status, actual_activity_id FROM weekly_prescriptions"
        ).fetchall()
    return {title: (status, activity_id) for title, status, activity_id in rows}


@pytest.mark.unit
def test_reconcile_marks_done_within_tolerance(db_path: str) -> None:
    """A 21.4 km run against a 22.0 km long run is inside tolerance -> done."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "long", target_km=22.0)],
        db_path=db_path,
    )
    _add_activity(db_path, 111, "2026-09-10", 21.4, 140.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result == {"updated": 1, "done": 1, "replaced": 0, "skipped": 0}
    assert _statuses(db_path)["long 2026-09-10"] == ("done", 111)


@pytest.mark.unit
def test_reconcile_marks_replaced_when_far_off(db_path: str) -> None:
    """An 8 km run against a 22.0 km long run is out of tolerance -> replaced."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "long", target_km=22.0)],
        db_path=db_path,
    )
    _add_activity(db_path, 222, "2026-09-10", 8.0, 50.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["replaced"] == 1
    assert _statuses(db_path)["long 2026-09-10"] == ("replaced", 222)


@pytest.mark.unit
def test_reconcile_easy_registered_length_is_done(db_path: str) -> None:
    """An easy run done at the registered length (no bookends) is done (#1039)."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-09", "easy", target_minutes=45)],
        db_path=db_path,
    )
    _add_activity(db_path, 444, "2026-09-09", 7.2, 46.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["done"] == 1
    assert _statuses(db_path)["easy 2026-09-09"] == ("done", 444)


@pytest.mark.unit
def test_reconcile_easy_has_no_bookend_allowance(db_path: str) -> None:
    """An easy run has no bookends, so 60 min against 45 is 1.33x -> replaced."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-09", "easy", target_minutes=45)],
        db_path=db_path,
    )
    _add_activity(db_path, 555, "2026-09-09", 9.5, 60.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["replaced"] == 1
    assert _statuses(db_path)["easy 2026-09-09"] == ("replaced", 555)


@pytest.mark.unit
def test_reconcile_threshold_allows_bookends(db_path: str) -> None:
    """A 20-min threshold body registered with 15 min of bookends -> done at 35."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "threshold", target_minutes=20)],
        db_path=db_path,
    )
    _add_activity(db_path, 666, "2026-09-10", 6.5, 35.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["done"] == 1
    assert _statuses(db_path)["threshold 2026-09-10"] == ("done", 666)


@pytest.mark.unit
def test_reconcile_threshold_body_only_is_out_of_band(db_path: str) -> None:
    """Running only the 20-min body misses the warmup/cooldown -> replaced."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "threshold", target_minutes=20)],
        db_path=db_path,
    )
    _add_activity(db_path, 777, "2026-09-10", 4.0, 20.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["replaced"] == 1
    assert _statuses(db_path)["threshold 2026-09-10"] == ("replaced", 777)


@pytest.mark.unit
def test_reconcile_pick_activity_uses_allowance_on_multi_run_day(
    db_path: str,
) -> None:
    """On a two-run day the bookend-sized run wins over the longest one."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "threshold", target_minutes=20)],
        db_path=db_path,
    )
    _add_activity(db_path, 888, "2026-09-10", 13.0, 70.0)
    _add_activity(db_path, 889, "2026-09-10", 6.5, 35.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["done"] == 1
    assert _statuses(db_path)["threshold 2026-09-10"] == ("done", 889)


@pytest.mark.unit
def test_reconcile_marks_skipped_when_no_run_past(db_path: str) -> None:
    """A past easy run with no activity at all -> skipped."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-09", "easy", target_minutes=50)],
        db_path=db_path,
    )

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result == {"updated": 1, "done": 0, "replaced": 0, "skipped": 1}
    assert _statuses(db_path)["easy 2026-09-09"] == ("skipped", None)


@pytest.mark.unit
def test_reconcile_rest_with_run_is_replaced(db_path: str) -> None:
    """Running on a rest day is a replacement, not compliance."""
    insert_weekly_prescriptions(
        WEEK_START, [_prescription("2026-09-10", "rest")], db_path=db_path
    )
    _add_activity(db_path, 333, "2026-09-10", 6.0, 40.0)

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    assert result["replaced"] == 1
    assert _statuses(db_path)["rest 2026-09-10"] == ("replaced", 333)


@pytest.mark.unit
def test_reconcile_leaves_future_untouched(db_path: str) -> None:
    """A prescription dated after today keeps its prescribed status."""
    insert_weekly_prescriptions(
        "2026-09-14",
        [_prescription("2026-09-20", "easy", target_minutes=50)],
        db_path=db_path,
    )

    result = reconcile_prescriptions(
        "2026-09-14", "2026-09-20", today=TODAY, db_path=db_path
    )

    assert result == {"updated": 0, "done": 0, "replaced": 0, "skipped": 0}
    assert _statuses(db_path)["easy 2026-09-20"] == ("prescribed", None)


@pytest.mark.unit
def test_reconcile_ignores_superseded_batches(db_path: str) -> None:
    """Rows of an older batch are history and stay prescribed."""
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-09", "easy", target_minutes=50)],
        db_path=db_path,
    )
    insert_weekly_prescriptions(
        WEEK_START,
        [_prescription("2026-09-10", "threshold", target_minutes=45)],
        db_path=db_path,
    )

    result = reconcile_prescriptions(
        "2026-09-07", "2026-09-13", today=TODAY, db_path=db_path
    )

    statuses = _statuses(db_path)
    assert result["updated"] == 1
    assert statuses["easy 2026-09-09"] == ("prescribed", None)
    assert statuses["threshold 2026-09-10"] == ("skipped", None)
