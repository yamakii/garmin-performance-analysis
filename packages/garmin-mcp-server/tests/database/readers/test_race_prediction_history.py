"""Tests for RaceReader.get_race_prediction_history() (Issue #1133).

There is no stored prediction history: the series is derived by applying
``VDOTCalculator.predict_race_time`` to the objective fitness curve's dated
VDOT points (or, when no splits exist, to Garmin's VO2max series). The
integration tests therefore build a tmp DuckDB (schema via ``reader_db_path``)
with the inputs each source needs; the goal-shape tests are unit-level because
they return before any curve is read.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.race import RaceReader
from garmin_mcp.fitness.vdot import VDOTCalculator

_MARATHON_KM = 42.195


def _insert_run(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    split_seconds: float,
    n_splits: int = 6,
) -> None:
    """Insert one activity + ``n_splits`` 1 km laps (km-unit ``distance``)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                float(n_splits),
                int(split_seconds * n_splits),
                split_seconds,
                150,
            ],
        )
        for index in range(n_splits):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds
                ) VALUES (?, ?, ?, ?)
                """,
                [activity_id, index, 1.0, split_seconds],
            )
    finally:
        conn.close()


def _insert_vo2max(
    db_path: Path, *, activity_id: int, value: float, measured_on: str
) -> None:
    """Insert one ``vo2_max`` row (the Garmin fallback's only input)."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO vo2_max (activity_id, precise_value, value, date, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            [activity_id, value, value, measured_on, 5],
        )
    finally:
        conn.close()


def _insert_goal(
    db_path: Path,
    *,
    race_name: str = "さいたまマラソン",
    race_date: str | None = None,
    distance_km: float | None = _MARATHON_KM,
    target_time_seconds: int | None = 12000,
) -> None:
    """Insert a single active priority-A goal."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_athlete_goals_id START 1")
        conn.execute(
            """
            INSERT INTO athlete_goals (
                goal_id, user_id, race_name, race_date, priority,
                goal_type, distance_km, target_time_seconds, status, notes
            ) VALUES (
                nextval('seq_athlete_goals_id'), ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                "default",
                race_name,
                race_date or (date.today() + timedelta(days=180)).isoformat(),
                "A",
                "marathon",
                distance_km,
                target_time_seconds,
                "active",
                None,
            ],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_race_prediction_history_from_objective_curve(reader_db_path: Path) -> None:
    """Three days of splits + an A race -> an objective-sourced series."""
    for offset, (activity_id, split_seconds) in enumerate(
        [(7001, 300.0), (7002, 295.0), (7003, 290.0)]
    ):
        _insert_run(
            reader_db_path,
            activity_id=activity_id,
            activity_date=f"2026-04-{10 + offset:02d}",
            split_seconds=split_seconds,
        )
    _insert_goal(reader_db_path, target_time_seconds=12000)

    # Fixed dates + the widest window, so the assertion does not decay as the
    # calendar moves past the default trailing year.
    result = RaceReader(db_path=str(reader_db_path)).get_race_prediction_history(
        days=3650
    )

    assert result["source"] == "objective"
    assert result["goal"]["target_time_seconds"] == 12000

    series = result["series"]
    assert len(series) == 3
    # Ascending by date, one point per run day.
    dates = [point["date"] for point in series]
    assert dates == sorted(dates)
    assert dates == ["2026-04-10", "2026-04-11", "2026-04-12"]

    for point in series:
        expected = VDOTCalculator.predict_race_time(point["vdot"], _MARATHON_KM)
        assert point["predicted_time_seconds"] == expected
        assert point["gap_seconds"] == expected - 12000


@pytest.mark.integration
def test_race_prediction_history_falls_back_to_garmin(reader_db_path: Path) -> None:
    """No splits -> the single vo2_max row drives a garmin_vo2max series."""
    _insert_vo2max(
        reader_db_path, activity_id=7101, value=52.0, measured_on="2026-05-01"
    )
    _insert_goal(reader_db_path, target_time_seconds=12000)

    result = RaceReader(db_path=str(reader_db_path)).get_race_prediction_history(
        days=3650
    )

    assert result["source"] == "garmin_vo2max"
    series = result["series"]
    assert len(series) == 1
    point = series[0]
    assert point["date"] == "2026-05-01"
    assert point["vdot"] == round(VDOTCalculator.vdot_from_vo2max(52.0), 1)
    expected = VDOTCalculator.predict_race_time(point["vdot"], _MARATHON_KM)
    assert point["predicted_time_seconds"] == expected
    assert point["gap_seconds"] == expected - 12000


@pytest.mark.integration
def test_race_prediction_history_trailing_window(reader_db_path: Path) -> None:
    """Only points inside the trailing window are plotted."""
    old_date = (date.today() - timedelta(days=400)).isoformat()
    recent_date = (date.today() - timedelta(days=10)).isoformat()
    _insert_vo2max(reader_db_path, activity_id=7301, value=48.0, measured_on=old_date)
    _insert_vo2max(
        reader_db_path, activity_id=7302, value=52.0, measured_on=recent_date
    )
    _insert_goal(reader_db_path, target_time_seconds=12000)

    reader = RaceReader(db_path=str(reader_db_path))

    windowed = reader.get_race_prediction_history(days=365)
    assert [point["date"] for point in windowed["series"]] == [recent_date]

    full = reader.get_race_prediction_history(days=3650)
    assert [point["date"] for point in full["series"]] == [old_date, recent_date]


@pytest.mark.unit
def test_race_prediction_history_no_goal(reader_db_path: Path) -> None:
    """Without a goal row there is nothing to predict against."""
    result = RaceReader(db_path=str(reader_db_path)).get_race_prediction_history()

    assert result == {"goal": None, "source": None, "series": []}


@pytest.mark.unit
def test_race_prediction_history_goal_without_target(reader_db_path: Path) -> None:
    """A goal without a target time is echoed back, but the gap is undefined."""
    _insert_vo2max(
        reader_db_path, activity_id=7201, value=52.0, measured_on="2026-05-01"
    )
    _insert_goal(reader_db_path, target_time_seconds=None)

    result = RaceReader(db_path=str(reader_db_path)).get_race_prediction_history()

    assert result["goal"]["race_name"] == "さいたまマラソン"
    assert result["goal"]["target_time_seconds"] is None
    assert result["source"] is None
    assert result["series"] == []
