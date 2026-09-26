"""Tests for carrying a Garmin registration across prescription batches (#1447).

A revised week is saved as a new batch. A new row that would put the same
workout on the watch as the superseded batch's registered row on that date
keeps the registration (status and Garmin ids); a row whose workout changed is
listed for re-registration instead, and a carried workout is live, so it is
never reported as superseded.

Split out of ``test_plan.py`` to keep both files under the test-size budget.
Uses the module-scoped ``initialized_db_path`` fixture, so each test owns its
week.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.inserters.plan import (
    insert_weekly_prescriptions,
    update_prescription_status,
)

_WORKOUT_ID = 1705499185
_SCHEDULE_ID = 1784857432


def _long_28(on_date: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": on_date,
        "session_type": "long",
        "title": "ロング28km（新潟最終ロング）",
        "target_minutes": None,
        "target_km": 28.0,
        "hr_low": None,
        "hr_high": 150,
        "rationale": "ラダー最終段",
    }
    row.update(overrides)
    return row


def _register_first_batch(db_path: str, week_start: str, on_date: str) -> None:
    """Save a one-row batch and mark it registered on Garmin."""
    saved = insert_weekly_prescriptions(
        week_start, [_long_28(on_date)], db_path=db_path
    )
    update_prescription_status(
        saved["prescription_ids"][0],
        "registered",
        garmin_workout_id=_WORKOUT_ID,
        garmin_schedule_id=_SCHEDULE_ID,
        registered_bookend_minutes=0,
        db_path=db_path,
    )


def _registration(db_path: str, prescription_id: int) -> tuple[Any, ...]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status, garmin_workout_id, garmin_schedule_id, "
            "registered_bookend_minutes FROM weekly_prescriptions "
            "WHERE prescription_id = ?",
            [prescription_id],
        ).fetchone()
    assert row is not None
    return tuple(row)


@pytest.mark.integration
def test_insert_carries_registration_for_unchanged_row(
    initialized_db_path: Path,
) -> None:
    """A judge-only edit keeps the row's Garmin registration."""
    db_path = str(initialized_db_path)
    _register_first_batch(db_path, "2026-09-21", "2026-09-27")

    saved = insert_weekly_prescriptions(
        "2026-09-21",
        [_long_28("2026-09-27", rationale="補給は45分ごと", allowances={"walk": True})],
        db_path=db_path,
    )
    new_id = saved["prescription_ids"][0]

    assert saved["carried_registrations"] == [
        {
            "prescription_id": new_id,
            "date": "2026-09-27",
            "garmin_schedule_id": _SCHEDULE_ID,
        }
    ]
    assert saved["needs_reregistration"] == []
    assert _registration(db_path, new_id) == (
        "registered",
        _WORKOUT_ID,
        _SCHEDULE_ID,
        0,
    )


@pytest.mark.integration
def test_insert_does_not_carry_changed_row(initialized_db_path: Path) -> None:
    """A different HR ceiling is a different workout: re-register it."""
    db_path = str(initialized_db_path)
    _register_first_batch(db_path, "2026-09-28", "2026-10-04")

    saved = insert_weekly_prescriptions(
        "2026-09-28", [_long_28("2026-10-04", hr_high=145)], db_path=db_path
    )
    new_id = saved["prescription_ids"][0]

    assert saved["carried_registrations"] == []
    assert saved["needs_reregistration"] == [
        {"prescription_id": new_id, "date": "2026-10-04"}
    ]
    assert _registration(db_path, new_id) == ("prescribed", None, None, None)


@pytest.mark.integration
def test_insert_keeps_explicit_status(initialized_db_path: Path) -> None:
    """A status the caller set is not overwritten by a carried registration."""
    db_path = str(initialized_db_path)
    _register_first_batch(db_path, "2026-10-05", "2026-10-11")

    saved = insert_weekly_prescriptions(
        "2026-10-05", [_long_28("2026-10-11", status="skipped")], db_path=db_path
    )
    new_id = saved["prescription_ids"][0]

    assert saved["carried_registrations"] == []
    assert saved["needs_reregistration"] == []
    assert _registration(db_path, new_id) == ("skipped", None, None, None)


@pytest.mark.integration
def test_superseded_ids_exclude_live_carried_workout(
    initialized_db_path: Path,
) -> None:
    """A carried workout is live, so a same-day registration never replaces it."""
    from garmin_mcp.database.readers.plan import PlanReader

    db_path = str(initialized_db_path)
    _register_first_batch(db_path, "2026-10-12", "2026-10-18")
    insert_weekly_prescriptions(
        "2026-10-12",
        [_long_28("2026-10-18", rationale="理由だけ更新")],
        db_path=db_path,
    )

    superseded = PlanReader(db_path=db_path).get_superseded_workout_ids("2026-10-12")

    assert _WORKOUT_ID not in superseded.get("2026-10-18", [])
