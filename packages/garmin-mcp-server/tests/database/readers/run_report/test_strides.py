"""Strides on the plan card and the HR ceiling judged on the jog (#1297).

An easy run with strides answers two things: the easy jog (its HR ceiling) and
the strides themselves (how many were run). A stride is meant to clear the
easy ceiling, so the ceiling's ``seconds_over`` is read off the heart-rate time
series with the stride laps (and the HR recovery after them) masked out --
the steady-running mask of #1313, see ``test_ceiling_windows.py``.
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
    _seed_zones,
)

# ``(distance_km, duration_s, role_phase, avg_hr)`` laps.
_Lap = tuple[float, float, str, float]

_JOG: list[_Lap] = [(1.0, 420.0, "run", 145.0) for _ in range(3)]
_COOLDOWN: _Lap = (0.65, 300.0, "cooldown", 138.0)


def _strides(reps: int, *, stride_s: float = 20.0, jog_s: float = 90.0) -> list[_Lap]:
    """``reps`` x (stride / jog-recovery) laps."""
    laps: list[_Lap] = []
    for _ in range(reps):
        laps.append((0.095, stride_s, "stride", 160.0))
        laps.append((0.19, jog_s, "recovery", 160.0))
    return laps


def _seed_laps(db_path: Path, activity_id: int, laps: list[_Lap]) -> None:
    """Replace one run's splits with timed laps (``start_time_s`` / ``end_time_s``)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])
        elapsed = 0.0
        for index, (distance, duration, role, avg_hr) in enumerate(laps, start=1):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, intensity_type, role_phase,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 178.0, 1.0, 1.0)
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
                    avg_hr,
                    avg_hr + 4,
                ],
            )
            elapsed += duration
    finally:
        conn.close()


def _seed_hr_series(db_path: Path, activity_id: int, laps: list[_Lap]) -> None:
    """One HR sample per second, each lap at its own ``avg_hr``."""
    conn = duckdb.connect(str(db_path))
    try:
        rows: list[tuple[int, int, int, float]] = []
        second = 0
        for _distance, duration, _role, avg_hr in laps:
            for _ in range(int(duration)):
                rows.append((activity_id, second, second, avg_hr))
                second += 1
        conn.executemany(
            """
            INSERT INTO time_series_metrics (
                activity_id, seq_no, timestamp_s, heart_rate
            ) VALUES (?, ?, ?, ?)
            """,
            rows,
        )
    finally:
        conn.close()


def _set_strides(db_path: Path, strides: dict[str, int]) -> None:
    """Attach a ``strides`` add-on to the seeded prescription."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE weekly_prescriptions SET strides = ?", [json.dumps(strides)]
        )
    finally:
        conn.close()


def _seed_today(db_path: Path, laps: list[_Lap], *, strides: bool = True) -> None:
    """History, today's run with ``laps``, and an easy prescription (ceiling 150)."""
    _seed_history(db_path)
    _seed_run(
        db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=146,
        distance_km=sum(lap[0] for lap in laps),
        duration_s=int(sum(lap[1] for lap in laps)),
    )
    _seed_laps(db_path, ACTIVITY_ID, laps)
    _seed_prescription(
        db_path,
        on_date=TODAY,
        session_type="easy",
        title="イージー 30分 + 流し",
        target_km=None,
        target_minutes=int(sum(lap[1] for lap in laps) / 60),
        hr_high=150,
    )
    if strides:
        _set_strides(db_path, {"reps": 4, "run_seconds": 20, "recovery_seconds": 90})


def _strides_check(report: dict) -> dict | None:
    return next((c for c in report["plan"]["checks"] if c["axis"] == "strides"), None)


@pytest.mark.integration
def test_plan_strides_axis_on_plan(reader_db_path: Path) -> None:
    """Four stride laps answer ``reps=4``; two leave the row short (🟡)."""
    _seed_today(reader_db_path, [*_JOG, *_strides(4), _COOLDOWN])

    report = _report(reader_db_path)

    assert report is not None
    check = _strides_check(report)
    assert check is not None
    assert check["target"] == "4本"
    assert check["actual"] == "4本"
    assert check["on_plan"] is True
    assert check["status"] == "on_plan"
    assert check["verdict"] == "✅"

    _seed_laps(reader_db_path, ACTIVITY_ID, [*_JOG, *_strides(2), _COOLDOWN])

    short = _report(reader_db_path)

    assert short is not None
    check = _strides_check(short)
    assert check is not None
    assert check["actual"] == "2本"
    assert check["on_plan"] is False
    assert check["status"] == "short"
    assert check["verdict"] == "🟡"


@pytest.mark.integration
def test_plan_strides_axis_absent_without_prescription_strides(
    reader_db_path: Path,
) -> None:
    """An easy prescription without strides has no strides row."""
    _seed_today(reader_db_path, [*_JOG, *_strides(4), _COOLDOWN], strides=False)

    report = _report(reader_db_path)

    assert report is not None
    assert report["plan"] is not None
    assert _strides_check(report) is None


@pytest.mark.integration
def test_hr_ceiling_seconds_over_excludes_stride_windows(
    reader_db_path: Path,
) -> None:
    """Jog at 145, strides + their jogs at 160 for 300 s: nothing over 150.

    The zones say otherwise (300 s above 150) -- they cannot tell a stride
    second from a jog second, which is why the time series is read instead.
    """
    laps = [*_JOG, *_strides(2, stride_s=30.0, jog_s=120.0), _COOLDOWN]
    _seed_today(reader_db_path, laps)
    _seed_hr_series(reader_db_path, ACTIVITY_ID, laps)
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 130, 300.0), (2, 130, 150, 1260.0), (3, 150, 170, 300.0)],
    )

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["bpm"] == 150
    assert ceiling["seconds_over"] == 0
    assert ceiling["pct_over"] == 0
    row = next(c for c in report["plan"]["checks"] if c["axis"] == "hr_ceiling")
    # Jog laps only: (3 x 420 s at 145 + 300 s at 138) / 1560 s = 143.7 bpm.
    assert row["actual"] == "144 bpm"
    assert row["on_plan"] is True
