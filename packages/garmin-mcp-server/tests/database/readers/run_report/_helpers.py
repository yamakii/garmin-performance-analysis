"""Shared fixtures for the run-report tests (split from test_run_report.py, #1069).

Every test builds a tmp DuckDB from the shared schema (``reader_db_path``) and
seeds runs through :func:`_seed_run`, so the reader is exercised against the
real tables it will read in production -- ``activities``, ``form_evaluations``,
``performance_trends``, ``hr_efficiency``, ``splits``, ``heart_rate_zones``,
``weekly_prescriptions`` and ``form_baseline_history``. No production data is
touched.

The baselines are seeded with *known* spread so a signal's z can be placed
deliberately: twelve prior runs alternating between two ground-contact
deviations give a median of 0.5 % and a robust spread of ``1.4826 * 0.5``, and
today's value is then written as ``centre + z * spread``.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from garmin_mcp.analysis.normal_range import MAD_SCALE
from garmin_mcp.database.db_reader import GarminDBReader

TODAY = "2025-10-09"
ACTIVITY_ID = 9100000001

# The gct deviations the twelve prior runs alternate between, and the band they
# imply (median / MAD-scaled spread) -- see the module docstring.
_BASELINE_LOW = 0.0
_BASELINE_HIGH = 1.0
_BASELINE_CENTRE = (_BASELINE_LOW + _BASELINE_HIGH) / 2
_BASELINE_SPREAD = MAD_SCALE * 0.5

# The vertical-ratio baseline of the same twelve runs (-0.5 / +0.5 %): centre 0,
# spread ``MAD_SCALE * 0.5``. The extrapolation tests place today in spreads of
# it, so a band that silently moved would fail rather than merely shift.
_VR_SPREAD = MAD_SCALE * 0.5

# Paces that put a run inside / far outside a 1.97-2.38 m/s trained range: the
# real 2026-09-09 pair, an easy run at 2.27 m/s and a tempo run at 2.70 m/s.
_INSIDE_RANGE_PACE = 440.0
_TEMPO_PACE = 1000.0 / 2.70

# The ``next_session`` fixtures work on real 2026 weekdays: 09-18 is a Friday,
# so 09-20 closes its week and 09-22 opens the next one.
NEXT_TODAY = "2026-09-18"
NEXT_ACTIVITY_ID = 9100000002


def _day(offset: int) -> str:
    """``TODAY`` shifted by ``offset`` days, as ``YYYY-MM-DD``."""
    return (date.fromisoformat(TODAY) + timedelta(days=offset)).isoformat()


def _seed_run(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    pace: float = 360.0,
    avg_hr: int | None = 140,
    temp_c: float = 15.0,
    distance_km: float = 8.0,
    duration_s: int = 2880,
    training_type: str = "aerobic_base",
    gct_delta_pct: float = 0.0,
    vr_delta_pct: float = 0.0,
    cadence_actual: float = 176.0,
    power_score: float = 0.95,
    hr_drift: float = 3.0,
    n_splits: int = 5,
    split_hr: int = 140,
) -> None:
    """Insert one complete run: activity, form, trends, zones split rows.

    The splits carry the form columns the extrapolation guard averages, so the
    run's evaluation speed is ``1000 / pace`` -- the speed a baseline's trained
    range is compared against (#1273).
    """
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate,
                temp_celsius, relative_humidity_percent, wind_speed_kmh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                distance_km,
                duration_s,
                pace,
                avg_hr,
                temp_c,
                62.0,
                7.2,
            ],
        )
        conn.execute(
            """
            INSERT INTO hr_efficiency (
                activity_id, primary_zone, training_type,
                zone1_percentage, zone2_percentage, zone3_percentage,
                zone4_percentage, zone5_percentage
            ) VALUES (?, 'Zone 2', ?, 15.0, 80.0, 5.0, 0.0, 0.0)
            """,
            [activity_id, training_type],
        )
        conn.execute(
            """
            INSERT INTO form_evaluations (
                eval_id, activity_id,
                gct_ms_expected, gct_ms_actual, gct_delta_pct,
                vo_cm_expected, vo_cm_actual, vo_delta_cm,
                vr_pct_expected, vr_pct_actual, vr_delta_pct,
                cadence_expected, cadence_actual, cadence_delta_pct,
                power_efficiency_score
            ) VALUES (?, ?, 250.0, ?, ?, 7.8, 7.8, 0.0, 8.0, ?, ?,
                      176.0, ?, 0.0, ?)
            """,
            [
                activity_id % 1000000,
                activity_id,
                250.0 * (1 + gct_delta_pct / 100),
                gct_delta_pct,
                8.0 * (1 + vr_delta_pct / 100),
                vr_delta_pct,
                cadence_actual,
                power_score,
            ],
        )
        conn.execute(
            """
            INSERT INTO performance_trends (
                activity_id, hr_drift_percentage,
                warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                run_avg_pace_seconds_per_km, run_avg_hr,
                cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                hr_drift,
                pace + 20,
                None if avg_hr is None else avg_hr - 8,
                pace,
                avg_hr,
                pace + 30,
                None if avg_hr is None else avg_hr - 14,
            ],
        )
        for index in range(1, n_splits + 1):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss,
                    ground_contact_time, vertical_oscillation, vertical_ratio
                ) VALUES (?, ?, 1.0, ?, ?, ?, ?, 176.0, 3.0, 3.0,
                          250.0, 7.8, 8.0)
                """,
                [
                    activity_id,
                    index,
                    pace,
                    pace,
                    split_hr,
                    split_hr + 5,
                ],
            )
    finally:
        conn.close()


def _seed_splits(
    db_path: Path,
    activity_id: int,
    rows: list[tuple[float, float, str | None]],
) -> None:
    """Replace one run's splits with ``(distance_km, duration_s, role_phase)``.

    Timing is written the way the device records it (``start_time_s`` /
    ``end_time_s``), so the reader's flow positions are exercised on the same
    columns production reads.
    """
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("DELETE FROM splits WHERE activity_id = ?", [activity_id])
        elapsed = 0.0
        for index, (distance, duration, role_phase) in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    start_time_s, end_time_s, intensity_type, role_phase,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, ?, ?, ?, ?, 'INTERVAL', ?, ?, 140, 148, 176.0,
                          3.0, 3.0)
                """,
                [
                    activity_id,
                    index,
                    distance,
                    duration,
                    elapsed,
                    elapsed + duration,
                    role_phase,
                    duration / distance,
                ],
            )
            elapsed += duration
    finally:
        conn.close()


def _seed_zones(
    db_path: Path,
    activity_id: int,
    zones: list[tuple[int, int, int, float]],
) -> None:
    """Insert ``(zone_number, low, high, seconds)`` rows for one activity."""
    total = sum(zone[3] for zone in zones)
    conn = duckdb.connect(str(db_path))
    try:
        for zone_number, low, high, seconds in zones:
            conn.execute(
                """
                INSERT INTO heart_rate_zones (
                    activity_id, zone_number, zone_low_boundary,
                    zone_high_boundary, time_in_zone_seconds, zone_percentage
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    activity_id,
                    zone_number,
                    low,
                    high,
                    seconds,
                    round(seconds / total * 100, 1) if total else 0.0,
                ],
            )
    finally:
        conn.close()


def _seed_prescription(
    db_path: Path,
    *,
    on_date: str,
    session_type: str = "easy",
    title: str = "イージー 8km",
    target_km: float | None = 8.0,
    target_minutes: int | None = None,
    hr_low: int | None = 130,
    hr_high: int | None = 150,
    status: str = "prescribed",
    prescription_id: int = 1,
) -> None:
    """Insert one prescription in the week its date belongs to.

    ``prescription_id`` is explicit so a test can write a whole week: the plan
    reader returns the latest batch of each week, and "what is next" has to walk
    several rows to find the next *run* (#1273).
    """
    day = date.fromisoformat(on_date)
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO weekly_prescriptions (
                prescription_id, batch_id, user_id, review_id,
                week_start_date, date, session_type, title, target_km,
                target_minutes, hr_low, hr_high, status
            ) VALUES (?, 1, 'default', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                prescription_id,
                week_start,
                on_date,
                session_type,
                title,
                target_km,
                target_minutes,
                hr_low,
                hr_high,
                status,
            ],
        )
    finally:
        conn.close()


def _seed_history(db_path: Path, count: int = 12, pace_base: float = 340.0) -> None:
    """Seed ``count`` prior same-family runs with a known gct / HR baseline.

    Pace, temperature and date are varied independently so the heat-adjustment
    regression has three non-collinear inputs, and the seeded heart rate is the
    model's own linear form plus an alternating +-1 bpm, which gives the HR
    residual a small but non-zero spread to judge today against. The power
    score alternates for the same reason: a constant series has no spread and
    could never judge anything.

    ``pace_base`` moves the whole block: the extrapolation tests need a history
    that sits *inside* a trained speed range, the rest do not care.
    """
    for index in range(count):
        pace = pace_base + 10 * ((index * 5) % 7)
        temp_c = 10.0 + ((index * 3) % 11)
        modelled = 120 + 0.06 * pace + 0.7 * max(temp_c - 15.0, 0.0)
        even = index % 2 == 0
        _seed_run(
            db_path,
            activity_id=ACTIVITY_ID + 100 + index,
            activity_date=_day(-3 * (count - index)),
            pace=pace,
            temp_c=temp_c,
            avg_hr=int(round(modelled)) + (1 if even else -1),
            gct_delta_pct=_BASELINE_LOW if even else _BASELINE_HIGH,
            vr_delta_pct=-0.5 if even else 0.5,
            power_score=0.94 if even else 0.96,
        )


def _seed_baseline(
    db_path: Path,
    *,
    speed_min: float,
    speed_max: float,
    period_start: str = "2000-01-01",
    period_end: str = "2100-01-01",
) -> None:
    """Insert a form baseline whose window covers every seeded run's date.

    Only the trained speed range matters here: the run report reads it to decide
    whether a run's expectations were extrapolations (#1273), never to predict.
    """
    conn = duckdb.connect(str(db_path))
    try:
        for index, metric in enumerate(("gct", "vo", "vr", "cadence")):
            conn.execute(
                """
                INSERT INTO form_baseline_history (
                    history_id, user_id, condition_group, metric, model_type,
                    coef_a, coef_b, period_start, period_end, n_samples, rmse,
                    speed_range_min, speed_range_max
                ) VALUES (?, 'default', 'flat_road', ?, 'linear',
                          1.0, 0.0, ?, ?, 150, 0.2, ?, ?)
                """,
                [
                    index + 1,
                    metric,
                    period_start,
                    period_end,
                    speed_min,
                    speed_max,
                ],
            )
    finally:
        conn.close()


def _report(db_path: Path, activity_id: int = ACTIVITY_ID) -> dict[str, Any] | None:
    """Run the reader through the unified ``GarminDBReader`` delegation."""
    return GarminDBReader(str(db_path)).get_run_report(activity_id)


def _signal(report: dict[str, Any], metric: str) -> dict[str, Any]:
    """The one signal named ``metric``."""
    return next(s for s in report["signals"] if s["metric"] == metric)
