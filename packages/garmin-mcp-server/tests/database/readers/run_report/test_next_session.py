"""What the athlete actually does next (#1273).

``next_run_target`` describes the next run *of this kind*; ``next_session``
answers the calendar's question instead, in order of how much is known: the next
prescribed run, the next long-run ladder step, then a dateless projection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    NEXT_ACTIVITY_ID,
    NEXT_TODAY,
    _report,
    _seed_prescription,
    _seed_run,
)


@pytest.mark.integration
def test_next_session_prefers_the_scheduled_prescription(
    reader_db_path: Path,
) -> None:
    """What is next is the next prescribed *run*, not the next run of this kind.

    The 09-19 strength row cannot be answered by going for a run, so the long
    run two days out is what the athlete does next (#1267).
    """
    _seed_run(reader_db_path, activity_id=NEXT_ACTIVITY_ID, activity_date=NEXT_TODAY)
    _seed_prescription(reader_db_path, on_date=NEXT_TODAY, prescription_id=1)
    _seed_prescription(
        reader_db_path,
        on_date="2026-09-19",
        session_type="strength",
        title="補強 30分",
        target_km=None,
        target_minutes=30,
        hr_low=None,
        hr_high=None,
        prescription_id=2,
    )
    _seed_prescription(
        reader_db_path,
        on_date="2026-09-20",
        session_type="long",
        title="ロング 16km",
        target_km=16.0,
        hr_high=150,
        prescription_id=3,
    )

    report = _report(reader_db_path, activity_id=NEXT_ACTIVITY_ID)

    assert report is not None
    assert report["next_session"] == {
        "date": "2026-09-20",
        "days_ahead": 2,
        "session_type": "long",
        "session_label_ja": "イージー（ロング走）",
        "title": "ロング 16km",
        "target_km": 16.0,
        "target_minutes": None,
        "hr_low": 130,
        "hr_high": 150,
        "source": "prescription",
    }


@pytest.mark.integration
def test_next_session_skips_skipped_rows(reader_db_path: Path) -> None:
    """A session already marked skipped is not what happens next."""
    _seed_run(reader_db_path, activity_id=NEXT_ACTIVITY_ID, activity_date=NEXT_TODAY)
    _seed_prescription(
        reader_db_path,
        on_date="2026-09-20",
        session_type="long",
        title="ロング 16km",
        target_km=16.0,
        status="skipped",
        prescription_id=1,
    )
    _seed_prescription(
        reader_db_path,
        on_date="2026-09-22",
        session_type="easy",
        title="イージー 8km",
        prescription_id=2,
    )

    report = _report(reader_db_path, activity_id=NEXT_ACTIVITY_ID)

    assert report is not None
    assert report["next_session"]["date"] == "2026-09-22"
    assert report["next_session"]["session_type"] == "easy"
    assert report["next_session"]["days_ahead"] == 4


@pytest.mark.integration
def test_next_session_falls_back_to_same_type(reader_db_path: Path) -> None:
    """With no plan at all, the next run of this kind is all that is known."""
    _seed_run(reader_db_path, activity_id=NEXT_ACTIVITY_ID, activity_date=NEXT_TODAY)

    report = _report(reader_db_path, activity_id=NEXT_ACTIVITY_ID)

    assert report is not None
    next_session = report["next_session"]
    assert next_session["source"] == "same_type"
    assert next_session["date"] is None
    assert next_session["hr_low"] == report["next_run_target"]["target_hr_low"]
    assert next_session["hr_high"] == report["next_run_target"]["target_hr_high"]


@pytest.mark.integration
def test_next_session_none_when_nothing_known(reader_db_path: Path) -> None:
    """No plan and no usable target: the report says nothing rather than guess."""
    _seed_run(
        reader_db_path,
        activity_id=NEXT_ACTIVITY_ID,
        activity_date=NEXT_TODAY,
        avg_hr=None,
    )

    report = _report(reader_db_path, activity_id=NEXT_ACTIVITY_ID)

    assert report is not None
    assert report["next_session"] is None
