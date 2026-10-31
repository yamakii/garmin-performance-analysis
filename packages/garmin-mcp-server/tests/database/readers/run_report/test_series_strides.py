"""Strides the laps do not mark, and strides carried over from a missed day (#1494).

A free run with manual laps carries no stride roles, so the report reads its
strides off the time series. A day whose prescribed strides no run did hands
them to the next run, which is judged on them.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _day,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)

# ``(seconds, speed m/s, cadence, hr)`` stretches of the time series.
_Segment = tuple[int, float, float, float]

_JOG: _Segment = (1200, 2.38, 178.0, 145.0)
_TAIL: _Segment = (300, 2.38, 178.0, 145.0)


def _strides(reps: int, *, hr: float = 160.0) -> list[_Segment]:
    out: list[_Segment] = []
    for _ in range(reps):
        out += [(20, 5.0, 205.0, hr), (90, 2.2, 175.0, hr)]
    return out


def _seed_series(db_path: Path, activity_id: int, segments: list[_Segment]) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        rows = []
        t = 0
        for seconds, speed, cadence, hr in segments:
            for _ in range(seconds):
                rows.append((activity_id, t, t, hr, speed, cadence))
                t += 1
        conn.executemany(
            """
            INSERT INTO time_series_metrics (
                activity_id, seq_no, timestamp_s, heart_rate, speed, cadence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    finally:
        conn.close()


def _seed_laps(
    db_path: Path, activity_id: int, laps: list[tuple[float, float, str]]
) -> None:
    """Timed laps ``(distance_km, duration_s, role_phase)``."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])
        elapsed = 0.0
        for index, (distance, duration, role) in enumerate(laps, start=1):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, intensity_type, role_phase,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, 146, 165, 178.0, 1.0, 1.0)
                """,
                [
                    activity_id,
                    index,
                    distance,
                    duration,
                    elapsed,
                    elapsed + duration,
                    role,
                    duration / distance,
                ],
            )
            elapsed += duration
    finally:
        conn.close()


# Three jog laps, then one manual lap holding the strides and the jog after.
_MANUAL_LAPS = [
    (0.952, 400.0, "run"),
    (0.952, 400.0, "run"),
    (0.952, 400.0, "run"),
    (1.906, 740.0, "run"),
]


def _seed_today(
    db_path: Path,
    *,
    target_minutes: int = 32,
    strides_column: dict | None = None,
    laps: list[tuple[float, float, str]] | None = None,
    segments: list[_Segment] | None = None,
) -> None:
    _seed_history(db_path)
    _seed_run(
        db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=146,
        distance_km=4.762,
        duration_s=1940,
    )
    _seed_laps(db_path, ACTIVITY_ID, laps or _MANUAL_LAPS)
    _seed_series(db_path, ACTIVITY_ID, segments or [_JOG, *_strides(4), _TAIL])
    _seed_prescription(
        db_path,
        on_date=TODAY,
        title=f"イージー {target_minutes}分",
        target_km=None,
        target_minutes=target_minutes,
        hr_low=None,
        hr_high=150,
        prescription_id=1,
    )
    if strides_column is not None:
        conn = duckdb.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE weekly_prescriptions SET strides = ? WHERE prescription_id = 1",
                [json.dumps(strides_column)],
            )
        finally:
            conn.close()


def _seed_yesterday_strides(db_path: Path) -> None:
    """Yesterday's easy run asked for 4 x 20 s strides."""
    _seed_prescription(
        db_path,
        on_date=_day(-1),
        title="イージー 35分＋流し 4本",
        target_km=None,
        target_minutes=35,
        hr_low=None,
        hr_high=150,
        prescription_id=2,
    )
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE weekly_prescriptions SET strides = ? WHERE prescription_id = 2",
            [json.dumps({"reps": 4, "run_seconds": 20, "recovery_seconds": 90})],
        )
    finally:
        conn.close()


def _check(report: dict, axis: str) -> dict | None:
    return next((c for c in report["plan"]["checks"] if c["axis"] == axis), None)


@pytest.mark.integration
def test_report_injects_series_strides_moment_when_laps_lack_roles(
    reader_db_path: Path,
) -> None:
    _seed_today(reader_db_path)

    report = _report(reader_db_path)

    assert report is not None
    strides = [m for m in report["moments"] if m["kind"] == "strides"]
    assert len(strides) == 1
    scene = strides[0]
    assert scene["facts"]["reps"] == 4
    assert scene["facts"]["source"] == "series"
    assert scene["t_from_s"] == 1200
    assert scene["split_from"] == 4
    assert not any(
        m["kind"] == "main" and m["t_from_s"] >= 1200 for m in report["moments"]
    )
    assert [m["id"] for m in report["moments"]] == [
        f"m{n}" for n in range(1, len(report["moments"]) + 1)
    ]


@pytest.mark.integration
def test_lap_strides_take_precedence_over_series(reader_db_path: Path) -> None:
    laps = [(0.952, 400.0, "run")] * 3
    for _ in range(4):
        laps += [(0.1, 20.0, "stride"), (0.198, 90.0, "recovery")]
    laps.append((0.714, 300.0, "run"))
    _seed_today(reader_db_path, laps=laps)

    report = _report(reader_db_path)

    assert report is not None
    strides = [m for m in report["moments"] if m["kind"] == "strides"]
    assert len(strides) == 1
    assert "source" not in strides[0]["facts"]
    assert strides[0]["facts"]["reps"] == 4


@pytest.mark.integration
def test_carried_strides_from_previous_day(reader_db_path: Path) -> None:
    _seed_today(reader_db_path, target_minutes=20)
    _seed_yesterday_strides(reader_db_path)

    report = _report(reader_db_path)

    assert report is not None
    check = _check(report, "strides")
    assert check is not None
    assert "持ち越し" in check["label_ja"]
    assert check["target"] == "4本"
    assert check["actual"] == "4本"
    assert check["status"] == "on_plan"
    # 20 min + 4 x (20 + 90) s = 27 min.
    volume = _check(report, "volume")
    assert volume is not None
    assert volume["target"] == "27分"
    assert "持ち越し" in report["plan"]["title"]


@pytest.mark.integration
def test_no_carry_when_previous_day_did_strides(reader_db_path: Path) -> None:
    _seed_today(reader_db_path, target_minutes=20)
    _seed_yesterday_strides(reader_db_path)
    yesterday_run = ACTIVITY_ID + 500
    _seed_run(
        reader_db_path,
        activity_id=yesterday_run,
        activity_date=_day(-1),
        distance_km=5.0,
        duration_s=2100,
    )
    _seed_series(reader_db_path, yesterday_run, [_JOG, *_strides(4), _TAIL])

    report = _report(reader_db_path)

    assert report is not None
    assert _check(report, "strides") is None
    assert "持ち越し" not in report["plan"]["title"]


@pytest.mark.integration
def test_no_carry_when_today_row_already_holds_the_strides(
    reader_db_path: Path,
) -> None:
    """A move written into today's row (daily-checkin) is not added twice."""
    _seed_today(reader_db_path, target_minutes=27)
    _seed_yesterday_strides(reader_db_path)
    structure = [
        {"step_type": "run", "duration_seconds": 1200, "hr_high": 150},
        {
            "repeat_count": 4,
            "steps": [
                {"step_type": "run", "duration_seconds": 20},
                {"step_type": "recovery", "duration_seconds": 90},
            ],
        },
    ]
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.execute(
            "UPDATE weekly_prescriptions SET structure = ? WHERE prescription_id = 1",
            [json.dumps(structure)],
        )
    finally:
        conn.close()

    report = _report(reader_db_path)

    assert report is not None
    assert "持ち越し" not in report["plan"]["title"]
    check = _check(report, "strides")
    assert check is not None
    assert check["target"] == "4本"
    assert check["actual"] == "4本"


@pytest.mark.integration
def test_ceiling_excludes_series_stride_windows(reader_db_path: Path) -> None:
    """Jog at 145, strides and their jogs at 160: nothing over the 150 ceiling."""
    _seed_today(reader_db_path)

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["bpm"] == 150
    assert ceiling["seconds_over"] == 0
