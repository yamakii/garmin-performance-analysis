"""``vs_previous`` never picks a fragment recorded after a run as "the previous run" (#1608).

On 2026-11-10 the report compared a 7 km pod run with a 0.41 km wrist-only
fragment recorded after the real 11/8 run, so the form deltas were dropped as
"another sensor" and pace / HR were compared with 400 m. What marks such a
fragment is a longer same-family run on the same day, so only each day's
longest run can be "the previous run"; a lone short run still counts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.run_report import _day_main_runs
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _day,
    _report,
    _seed_history,
    _seed_run,
)

_REAL_PREVIOUS = ACTIVITY_ID + 501
_FRAGMENT = ACTIVITY_ID + 502


@pytest.mark.integration
def test_vs_previous_skips_a_same_day_fragment(reader_db_path: Path) -> None:
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=_REAL_PREVIOUS,
        activity_date=_day(-2),
        pace=400.0,
        distance_km=5.1,
        n_splits=5,
    )
    # Recorded after the real run on the same day: higher activity id, 1 split.
    _seed_run(
        reader_db_path,
        activity_id=_FRAGMENT,
        activity_date=_day(-2),
        pace=438.0,
        avg_hr=131,
        distance_km=0.41,
        duration_s=180,
        n_splits=1,
    )
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    vs_previous = report["vs_previous"]
    assert vs_previous is not None
    assert vs_previous["previous_activity_id"] == _REAL_PREVIOUS
    assert vs_previous["pace_s_per_km"]["previous"] == pytest.approx(400.0)


@pytest.mark.integration
def test_vs_previous_keeps_a_lone_short_structured_run(reader_db_path: Path) -> None:
    """11/21's 20-minute jog with strides: one running split, still a run."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=_REAL_PREVIOUS,
        activity_date=_day(-1),
        distance_km=3.4,
        duration_s=1300,
        n_splits=1,
    )
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["vs_previous"]["previous_activity_id"] == _REAL_PREVIOUS


@pytest.mark.integration
def test_vs_previous_double_day_takes_the_longer_same_family_run(
    reader_db_path: Path,
) -> None:
    _seed_history(reader_db_path)
    longer = ACTIVITY_ID + 701
    _seed_run(
        reader_db_path,
        activity_id=longer,
        activity_date=_day(-1),
        distance_km=9.0,
        duration_s=3240,
    )
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID + 702,
        activity_date=_day(-1),
        distance_km=4.0,
        duration_s=1440,
    )
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["vs_previous"]["previous_activity_id"] == longer


@pytest.mark.unit
def test_day_main_runs_keeps_longest_per_day() -> None:
    runs = [
        {"activity_id": 10, "activity_date": "2026-11-08", "distance_km": 0.4},
        {"activity_id": 11, "activity_date": "2026-11-08", "distance_km": 5.1},
        {"activity_id": 12, "activity_date": "2026-11-08", "distance_km": 0.8},
        {"activity_id": 20, "activity_date": "2026-11-10", "distance_km": 7.0},
    ]
    kept = _day_main_runs(runs)
    assert [run["activity_id"] for run in kept] == [11, 20]
