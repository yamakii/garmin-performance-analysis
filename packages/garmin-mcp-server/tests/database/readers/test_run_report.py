"""Integration tests for the deterministic run report (#1250).

Every test builds a tmp DuckDB from the shared schema (``reader_db_path``) and
seeds runs through :func:`_seed_run`, so the reader is exercised against the
real tables it will read in production -- ``activities``, ``form_evaluations``,
``performance_trends``, ``hr_efficiency``, ``splits``, ``heart_rate_zones`` and
``weekly_prescriptions``. No production data is touched.

The baselines are seeded with *known* spread so a signal's z can be placed
deliberately: twelve prior runs alternating between two ground-contact
deviations give a median of 0.5 % and a robust spread of ``1.4826 * 0.5``, and
today's value is then written as ``centre + z * spread``.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

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


def _day(offset: int) -> str:
    """``TODAY`` shifted by ``offset`` days, as ``YYYY-MM-DD``."""
    return (date.fromisoformat(TODAY) + timedelta(days=offset)).isoformat()


def _seed_run(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    pace: float = 360.0,
    avg_hr: int = 140,
    temp_c: float = 15.0,
    distance_km: float = 8.0,
    duration_s: int = 2880,
    training_type: str = "aerobic_base",
    gct_delta_pct: float = 0.0,
    cadence_actual: float = 176.0,
    power_score: float = 0.95,
    hr_drift: float = 3.0,
    n_splits: int = 5,
    split_hr: int = 140,
) -> None:
    """Insert one complete run: activity, form, trends, zones split rows."""
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
            ) VALUES (?, ?, 250.0, ?, ?, 7.8, 7.8, 0.0, 8.0, 8.0, 0.0,
                      176.0, ?, 0.0, ?)
            """,
            [
                activity_id % 1000000,
                activity_id,
                250.0 * (1 + gct_delta_pct / 100),
                gct_delta_pct,
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
                avg_hr - 8,
                pace,
                avg_hr,
                pace + 30,
                avg_hr - 14,
            ],
        )
        for index in range(1, n_splits + 1):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss
                ) VALUES (?, ?, 1.0, ?, ?, ?, ?, 176.0, 3.0, 3.0)
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
    hr_low: int | None = 130,
    hr_high: int | None = 150,
) -> None:
    """Insert the day's prescription in the week its date belongs to."""
    day = date.fromisoformat(on_date)
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO weekly_prescriptions (
                prescription_id, batch_id, user_id, review_id,
                week_start_date, date, session_type, title, target_km,
                hr_low, hr_high, status
            ) VALUES (1, 1, 'default', 1, ?, ?, ?, ?, ?, ?, ?, 'prescribed')
            """,
            [
                week_start,
                on_date,
                session_type,
                title,
                target_km,
                hr_low,
                hr_high,
            ],
        )
    finally:
        conn.close()


def _seed_history(db_path: Path, count: int = 12) -> None:
    """Seed ``count`` prior same-family runs with a known gct / HR baseline.

    Pace, temperature and date are varied independently so the heat-adjustment
    regression has three non-collinear inputs, and the seeded heart rate is the
    model's own linear form plus an alternating +-1 bpm, which gives the HR
    residual a small but non-zero spread to judge today against.
    """
    for index in range(count):
        pace = 340.0 + 10 * ((index * 5) % 7)
        temp_c = 10.0 + ((index * 3) % 11)
        modelled = 120 + 0.06 * pace + 0.7 * max(temp_c - 15.0, 0.0)
        _seed_run(
            db_path,
            activity_id=ACTIVITY_ID + 100 + index,
            activity_date=_day(-3 * (count - index)),
            pace=pace,
            temp_c=temp_c,
            avg_hr=int(round(modelled)) + (1 if index % 2 == 0 else -1),
            gct_delta_pct=_BASELINE_LOW if index % 2 == 0 else _BASELINE_HIGH,
        )


def _report(db_path: Path, activity_id: int = ACTIVITY_ID) -> dict[str, Any] | None:
    """Run the reader through the unified ``GarminDBReader`` delegation."""
    return GarminDBReader(str(db_path)).get_run_report(activity_id)


def _signal(report: dict[str, Any], metric: str) -> dict[str, Any]:
    """The one signal named ``metric``."""
    return next(s for s in report["signals"] if s["metric"] == metric)


@pytest.mark.integration
def test_run_report_shape_and_json(reader_db_path: Path) -> None:
    """Every top-level key is present and the payload survives json.dumps."""
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 129, 400.0), (2, 130, 149, 1386.0), (3, 150, 159, 321.0)],
    )

    report = _report(reader_db_path)

    assert report is not None
    assert set(report) == {
        "activity_id",
        "activity_date",
        "intensity_category",
        "headline",
        "plan",
        "signals",
        "zones",
        "moments",
        "recurrence",
        "phases",
        "conditions",
        "vs_previous",
        "next_run_target",
    }
    assert report["activity_id"] == ACTIVITY_ID
    assert report["activity_date"] == TODAY
    assert report["intensity_category"] == "easy"
    assert len(report["signals"]) == 7
    assert [zone["zone"] for zone in report["zones"]] == [1, 2, 3]
    assert report["moments"], "an uneventful run still reports its steady scene"
    assert {phase["phase"] for phase in report["phases"]} == {
        "warmup",
        "run",
        "cooldown",
    }
    assert report["conditions"]["temp_c"] == 15.0
    assert report["vs_previous"] is not None

    # No custom encoder: dates are str and every number is a built-in.
    assert json.loads(json.dumps(report))["activity_id"] == ACTIVITY_ID


@pytest.mark.integration
def test_run_report_headline_no_flags(reader_db_path: Path) -> None:
    """A run that answers its prescription with no adverse signal is clean."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,  # 101 % of the 8.0 km target
        gct_delta_pct=_BASELINE_CENTRE,
    )
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 129, 400.0), (2, 130, 149, 1386.0), (3, 150, 159, 321.0)],
    )
    _seed_prescription(reader_db_path, on_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["headline"] == {
        "plan_label": "処方どおり",
        "flag_count": 0,
        "flag_labels": [],
    }
    assert report["plan"]["verdict"] == "✅"
    assert report["plan"]["title"] == "イージー 8km"
    volume = next(c for c in report["plan"]["checks"] if c["axis"] == "volume")
    assert volume == {
        "axis": "volume",
        "target": "8.0km",
        "actual": "8.1km（101%）",
        "status": "on_plan",
        "on_plan": True,
    }


@pytest.mark.integration
def test_run_report_flags_adverse_signal_only(reader_db_path: Path) -> None:
    """Only the unfavourable outlier becomes a flag; a favourable one does not."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        # +2.4 spreads on the unfavourable side of the seeded gct baseline.
        gct_delta_pct=_BASELINE_CENTRE + 2.4 * _BASELINE_SPREAD,
        # Far below what pace / temperature / date predict: an outlier the
        # athlete benefits from, so it must not be reported as a flag.
        avg_hr=110,
    )

    report = _report(reader_db_path)

    assert report is not None
    gct = _signal(report, "gct")
    assert gct["z"] == pytest.approx(2.4, abs=0.05)
    assert gct["status"] == "outside"
    assert gct["adverse"] is True

    hr = _signal(report, "hr_vs_expected")
    assert hr["status"] == "outside"
    assert hr["z"] < 0
    assert hr["adverse"] is False

    assert report["headline"]["flag_count"] == 1
    assert report["headline"]["flag_labels"] == ["接地時間が長め"]


@pytest.mark.integration
def test_run_report_without_prescription(reader_db_path: Path) -> None:
    """An unprescribed day has no plan card and says so in the headline."""
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["plan"] is None
    assert report["headline"]["plan_label"] == "処方なし"


@pytest.mark.integration
def test_run_report_hr_ceiling_from_prescription(reader_db_path: Path) -> None:
    """Time above the ceiling is read off the HR zones, not the time series."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,
    )
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [
            (1, 100, 129, 400.0),
            (2, 130, 149, 1386.0),
            (3, 150, 159, 321.0),  # 2107 s total, 321 s at or above 150 bpm
        ],
    )
    _seed_prescription(reader_db_path, on_date=TODAY, hr_high=150)

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["bpm"] == 150
    assert ceiling["seconds_over"] == 321.0
    assert ceiling["pct_over"] == pytest.approx(15.2, abs=0.2)


@pytest.mark.integration
def test_run_report_thin_history_is_insufficient_not_error(
    reader_db_path: Path,
) -> None:
    """Three prior runs judge nothing -- and raise nothing either."""
    _seed_history(reader_db_path, count=3)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert [signal["status"] for signal in report["signals"]] == ["insufficient"] * 7
    assert all(signal["reason"] for signal in report["signals"])
    assert report["headline"]["flag_count"] == 0


@pytest.mark.integration
def test_run_report_unknown_activity_returns_none(reader_db_path: Path) -> None:
    """An activity the database has never seen has no report."""
    assert _report(reader_db_path, activity_id=1) is None
