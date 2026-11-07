"""The recurrence look-back judges each previous run against its own ceiling (#1515).

The look-back re-detects the scenes of the previous same-family runs. It used
to judge all of them against *today's* ceiling, so a temporarily lowered
ceiling (a post-illness easy run at 135 after weeks at 150) turned every
earlier run into "touched the ceiling at km 1" and the report called it a
habit. A prescribed previous run is now judged against the ceiling it was run
under; an unprescribed one keeps today's, as before.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.run_report import (
    _existing_tables,
    _fetch_previous_ceilings,
)
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _day,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)

# _seed_history puts its 12 runs every third day, ending 3 days before TODAY;
# the look-back reads the last few of them.
_HISTORY_COUNT = 12
_PREVIOUS_OFFSETS = [-3 * n for n in range(1, 5)]


def _seed_today(db_path: Path, *, hr_high: int) -> None:
    """Today's easy run, all laps at HR 140, under the given ceiling."""
    _seed_history(db_path, count=_HISTORY_COUNT)
    _seed_run(db_path, activity_id=ACTIVITY_ID, activity_date=TODAY, split_hr=140)
    _seed_prescription(
        db_path,
        on_date=TODAY,
        session_type="easy",
        title="病み上がり イージー",
        target_km=None,
        target_minutes=30,
        hr_low=None,
        hr_high=hr_high,
        prescription_id=1,
    )


def _ceiling_rows(report: dict) -> list[dict]:
    return [row for row in report["recurrence"] if row["kind"] == "ceiling_touch"]


@pytest.mark.integration
def test_recurrence_uses_each_runs_own_ceiling(reader_db_path: Path) -> None:
    """Runs at HR 140 under their own 150 ceiling are not a 135-ceiling habit."""
    _seed_today(reader_db_path, hr_high=135)
    for index, offset in enumerate(_PREVIOUS_OFFSETS, start=2):
        _seed_prescription(
            reader_db_path,
            on_date=_day(offset),
            hr_low=None,
            hr_high=150,
            prescription_id=index,
        )

    report = _report(reader_db_path)

    assert report is not None
    # Today itself still crossed its own (lowered) ceiling ...
    assert "ceiling_touch" in [m["kind"] for m in report["moments"]]
    # ... but the runs before it did not cross theirs.
    assert _ceiling_rows(report) == []


@pytest.mark.integration
def test_recurrence_unprescribed_previous_keeps_today_ceiling(
    reader_db_path: Path,
) -> None:
    """Without a prescription of their own, previous runs keep today's ceiling."""
    _seed_today(reader_db_path, hr_high=135)

    report = _report(reader_db_path)

    assert report is not None
    assert _ceiling_rows(report), report["recurrence"]


@pytest.mark.integration
def test_fetch_previous_ceilings_latest_batch(reader_db_path: Path) -> None:
    """The latest batch of the week wins, and a 補強 row does not hide the run."""
    day = date.fromisoformat(TODAY)
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    conn = duckdb.connect(str(reader_db_path))
    try:
        rows = [
            # (prescription_id, batch_id, session_type, hr_high)
            (11, 1, "easy", 150),
            (12, 2, "strength", None),
            (13, 2, "easy", 145),
        ]
        for prescription_id, batch_id, session_type, hr_high in rows:
            conn.execute(
                """
                INSERT INTO weekly_prescriptions (
                    prescription_id, batch_id, user_id, review_id,
                    week_start_date, date, session_type, title, hr_high, status
                ) VALUES (?, ?, 'default', 1, ?, ?, ?, 't', ?, 'prescribed')
                """,
                [prescription_id, batch_id, week_start, TODAY, session_type, hr_high],
            )

        ceilings = _fetch_previous_ceilings(
            conn, _existing_tables(conn), [TODAY, _day(-1)]
        )
    finally:
        conn.close()

    assert ceilings == {TODAY: 145}
