"""The run's purpose and the per-scene policy verdicts on the report (#1314).

A walk break is judged against what the run was *for*: part of the deal on an
aerobic long run, a miss on a goal-pace rehearsal. The report exposes the
resolved purpose, a ``policy`` on every moment, and puts concern scenes in the
headline next to the adverse signals.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)

# A 14 km run at 6:00/km with a walk break in km 7 (walking cadence, +60 s/km).
_WALK_SPLIT = 7
_LONG_SPLITS = 14


def _seed_long_splits(db_path: Path, activity_id: int, *, walk_at: int | None) -> None:
    """Replace one run's splits with 1 km laps, one of them walked."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])
        for index in range(1, _LONG_SPLITS + 1):
            walked = index == walk_at
            pace = 420.0 if walked else 360.0
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, 1.0, ?, ?, 140, 145, ?, 2.0, 2.0)
                """,
                [activity_id, index, pace, pace, 140.0 if walked else 176.0],
            )
    finally:
        conn.close()


def _set_purpose(
    db_path: Path, purpose: str, allowances: dict[str, bool] | None = None
) -> None:
    """Declare a purpose (and optional allowances) on the seeded prescription."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE weekly_prescriptions SET purpose = ?, allowances = ?",
            [purpose, None if allowances is None else json.dumps(allowances)],
        )
    finally:
        conn.close()


def _seed_long_run(db_path: Path, *, duration_s: int = 5160) -> None:
    """History plus today's 14 km run with a walk break in km 7."""
    _seed_history(db_path)
    _seed_run(
        db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        distance_km=float(_LONG_SPLITS),
        duration_s=duration_s,
    )
    _seed_long_splits(db_path, ACTIVITY_ID, walk_at=_WALK_SPLIT)


def _walk_moment(report: dict) -> dict:
    return next(m for m in report["moments"] if m["kind"] == "walk_break")


@pytest.mark.integration
def test_report_exposes_purpose_and_policy(reader_db_path: Path) -> None:
    """A goal-pace long run: the walk break is a concern and is headlined."""
    _seed_long_run(reader_db_path)
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="long",
        title="ロング 14km 目標ペース",
        target_km=14.0,
    )
    _set_purpose(reader_db_path, "long_goal_pace")

    report = _report(reader_db_path)

    assert report is not None
    assert report["purpose"]["id"] == "long_goal_pace"
    assert report["purpose"]["label_ja"] == "ロング（目標ペース）"
    assert report["purpose"]["source"] == "prescription"
    # The run held its pace to the end, so it delivered what it was for.
    assert report["purpose"]["outcome"]["met"] is True
    walk = _walk_moment(report)
    assert walk["policy"]["verdict"] == "concern"
    assert walk["label_ja"] in report["headline"]["flag_labels"]
    assert report["headline"]["flag_count"] == len(report["headline"]["flag_labels"])
    assert all("policy" in moment for moment in report["moments"])
    json.dumps(report)

    # The same break on an aerobic long run is acceptable and not headlined.
    _set_purpose(reader_db_path, "long_easy")
    easy = _report(reader_db_path)

    assert easy is not None
    easy_walk = _walk_moment(easy)
    assert easy_walk["policy"]["verdict"] == "acceptable"
    assert easy_walk["label_ja"] not in easy["headline"]["flag_labels"]

    # An explicit allowance overrides the table.
    _set_purpose(reader_db_path, "long_goal_pace", {"walk": True})
    allowed = _report(reader_db_path)

    assert allowed is not None
    assert _walk_moment(allowed)["policy"]["verdict"] == "acceptable"


@pytest.mark.integration
def test_report_purpose_inferred_without_prescription(reader_db_path: Path) -> None:
    """A 120-minute easy run with no plan is read as an aerobic long run."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        distance_km=float(_LONG_SPLITS),
        duration_s=7200,
    )
    _seed_long_splits(reader_db_path, ACTIVITY_ID, walk_at=None)

    report = _report(reader_db_path)

    assert report is not None
    assert report["plan"] is None
    assert report["purpose"]["source"] == "inferred"
    assert report["purpose"]["id"] == "long_easy"


def _seed_mostly_collapsed_splits(db_path: Path, activity_id: int) -> None:
    """Only four kilometres held; the other ten came apart."""
    _seed_collapsing_splits(db_path, activity_id, held_until=4)


def _seed_collapsing_splits(
    db_path: Path, activity_id: int, *, held_until: int = 8
) -> None:
    """``held_until`` kilometres at 6:00/km, then the rest at 11:40/km."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])
        for index in range(1, _LONG_SPLITS + 1):
            collapsed = index > held_until
            pace = 700.0 if collapsed else 360.0
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, 1.0, ?, ?, ?, ?, ?, 2.0, 2.0)
                """,
                [
                    activity_id,
                    index,
                    pace,
                    pace,
                    108.0 if collapsed else 140.0,
                    115.0 if collapsed else 145.0,
                    120.0 if collapsed else 176.0,
                ],
            )
    finally:
        conn.close()


@pytest.mark.integration
def test_report_marks_a_run_that_missed_its_purpose(reader_db_path: Path) -> None:
    """A long run that came apart is a deviation, and it leads the headline.

    The heart rate falls with the pace here, which is exactly the run the old
    report read as "on plan, nicely aerobic": no scene was a concern, so the
    low zone share looked like the intended easy effort (#1340).
    """
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        distance_km=float(_LONG_SPLITS),
        duration_s=7200,
    )
    _seed_collapsing_splits(reader_db_path, ACTIVITY_ID)
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="long",
        title="ロング 14km",
        target_km=14.0,
    )
    _set_purpose(reader_db_path, "long_easy", {"walk": True})

    report = _report(reader_db_path)

    assert report is not None
    outcome = report["purpose"]["outcome"]
    assert outcome["met"] is False
    assert outcome["breakdown_from_km"] == 8.0
    breakdown = next(m for m in report["moments"] if m["kind"] == "breakdown")
    assert breakdown["policy"]["verdict"] == "concern"
    assert report["headline"]["flag_labels"][0] == breakdown["label_ja"]
    json.dumps(report)


@pytest.mark.integration
def test_next_run_target_uses_the_pace_the_run_held(reader_db_path: Path) -> None:
    """The next run's reference pace comes from the part that held (#1341).

    The whole-run average here is 6:25/km because six kilometres were spent
    at 11:40/km; the athlete's easy pace is the 6:00/km they ran for eight.
    """
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        distance_km=float(_LONG_SPLITS),
        duration_s=7200,
    )
    _seed_collapsing_splits(reader_db_path, ACTIVITY_ID)

    report = _report(reader_db_path)

    assert report is not None
    target = report["next_run_target"]
    assert target["reference_pace_low_formatted"] == "5:55/km"
    assert target["reference_pace_high_formatted"] == "6:05/km"


@pytest.mark.integration
def test_next_run_target_drops_pace_when_purpose_missed(reader_db_path: Path) -> None:
    """Under half the run held: there is no pace to repeat, only a HR range."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        distance_km=float(_LONG_SPLITS),
        duration_s=7200,
    )
    _seed_mostly_collapsed_splits(reader_db_path, ACTIVITY_ID)

    report = _report(reader_db_path)

    assert report is not None
    target = report["next_run_target"]
    assert report["purpose"]["outcome"]["sustained_share"] < 0.5
    assert not [key for key in target if key.startswith("reference_pace")]
    assert target["target_hr_low"] > 0
    assert target["target_hr_high"] > 0
