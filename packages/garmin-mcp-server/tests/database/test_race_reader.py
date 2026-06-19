"""Tests for VDOTCalculator predictions and RaceReader.get_race_readiness().

The VDOT prediction tests are unit-level regression guards on the rescued
``VDOTCalculator`` (#60). The readiness tests are integration-level: they build a
tmp DuckDB (schema via the ``reader_db_path`` fixture) populated with a single
activity + VO2max (so a VDOT is derivable) and, where relevant, an athlete goal.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.race import RaceReader
from garmin_mcp.training_plan.vdot import VDOTCalculator

# ---------------------------------------------------------------------------
# VDOTCalculator prediction regression (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_predict_full_from_vdot() -> None:
    """VDOT 48.2 predicts a full-marathon time around 3:16 (deterministic)."""
    seconds = VDOTCalculator.predict_race_time(48.2, 42.195)
    # Current rescued-asset output is 11798s (~3:16:38). Guard a tight band.
    assert 11700 <= seconds <= 11900


@pytest.mark.unit
def test_predict_10k_from_vdot() -> None:
    """VDOT 48.2 predicts a 10k time around 42:39 (deterministic)."""
    seconds = VDOTCalculator.predict_race_time(48.2, 10.0)
    # Current rescued-asset output is 2559s (~42:39). Guard a tight band.
    assert 2500 <= seconds <= 2600


# ---------------------------------------------------------------------------
# RaceReader.get_race_readiness() integration helpers
# ---------------------------------------------------------------------------


def _insert_activity_with_vo2max(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    vo2max: float,
) -> None:
    """Insert one running activity + its VO2max so a VDOT can be derived."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [activity_id, activity_date, 10.0, 3000, 300.0, 150],
        )
        conn.execute(
            "INSERT INTO vo2_max (activity_id, precise_value, value, date) "
            "VALUES (?, ?, ?, ?)",
            [activity_id, vo2max, vo2max, activity_date],
        )
    finally:
        conn.close()


def _insert_goal(
    db_path: Path,
    *,
    race_name: str,
    race_date: str | None,
    distance_km: float,
    target_time_seconds: int,
    priority: str = "A",
    status: str = "active",
    user_id: str = "default",
) -> None:
    """Insert a single athlete goal row."""
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
                user_id,
                race_name,
                race_date,
                priority,
                "race",
                distance_km,
                target_time_seconds,
                status,
                None,
            ],
        )
    finally:
        conn.close()


def _recent_date() -> str:
    """A date within the default 8-week lookback window."""
    return (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")


def _future_date(days: int = 200) -> str:
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# RaceReader.get_race_readiness() integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_readiness_with_active_goal(reader_db_path: Path) -> None:
    """VO2max + a future sub-4.5 goal yields a computed progress block."""
    _insert_activity_with_vo2max(
        reader_db_path, activity_id=111, activity_date=_recent_date(), vo2max=50.0
    )
    _insert_goal(
        reader_db_path,
        race_name="Saitama Marathon",
        race_date=_future_date(),
        distance_km=42.195,
        target_time_seconds=16200,  # sub-4.5
    )

    result = RaceReader(db_path=str(reader_db_path)).get_race_readiness()

    assert result["current_vdot"] is not None
    assert result["goal"]["race_name"] == "Saitama Marathon"
    assert result["goal"]["target_time_seconds"] == 16200

    progress = result["progress"]
    assert progress is not None
    expected_gap = progress["predicted_time_seconds"] - 16200
    assert progress["gap_seconds"] == expected_gap
    assert progress["status"] in {"ahead", "on_track", "behind"}
    assert progress["weeks_remaining"] is not None


@pytest.mark.integration
def test_readiness_no_goal_returns_predictions_only(reader_db_path: Path) -> None:
    """Without a goal, predictions are present but goal/progress are None."""
    _insert_activity_with_vo2max(
        reader_db_path, activity_id=222, activity_date=_recent_date(), vo2max=50.0
    )

    result = RaceReader(db_path=str(reader_db_path)).get_race_readiness()

    assert result["goal"] is None
    assert result["progress"] is None
    assert result["current_vdot"] is not None
    assert result["predicted_times"]  # non-empty
    assert set(result["predicted_times"]) == {"race_5k", "race_10k", "half", "full"}


@pytest.mark.integration
def test_readiness_no_vdot(reader_db_path: Path) -> None:
    """No activities/VO2max -> current_vdot None and empty predictions."""
    result = RaceReader(db_path=str(reader_db_path)).get_race_readiness()

    assert result["current_vdot"] is None
    assert result["predicted_times"] == {}
    assert result["progress"] is None


@pytest.mark.integration
def test_readiness_status_behind(reader_db_path: Path) -> None:
    """A target faster than the prediction yields status=behind, gap>0."""
    # Low fitness (vo2max=40 -> vdot 39.2, full ~14006s) vs an aggressive
    # sub-3:30 target (12600s): the prediction is far slower than target.
    _insert_activity_with_vo2max(
        reader_db_path, activity_id=333, activity_date=_recent_date(), vo2max=40.0
    )
    _insert_goal(
        reader_db_path,
        race_name="Ambitious Marathon",
        race_date=_future_date(),
        distance_km=42.195,
        target_time_seconds=12600,
    )

    result = RaceReader(db_path=str(reader_db_path)).get_race_readiness()

    progress = result["progress"]
    assert progress is not None
    assert progress["gap_seconds"] > 0
    assert progress["status"] == "behind"
