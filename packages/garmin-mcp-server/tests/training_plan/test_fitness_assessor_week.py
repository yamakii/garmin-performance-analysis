"""Integration tests for FitnessAssessor weekly aggregation.

These build a real DuckDB and exercise the gap-baseline weekly-volume median,
verifying it buckets by the configured week-start day (``week_start_day``;
Monday by default).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor


@pytest.fixture(scope="module")
def _fitness_schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with full schema pre-initialized."""
    tmp_path = tmp_path_factory.mktemp("fitness_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def fitness_db_path(_fitness_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB with full schema via file copy."""
    db_path = tmp_path / "fitness_test.duckdb"
    shutil.copy2(str(_fitness_schema_template), str(db_path))
    return db_path


def _insert_activity(
    conn: duckdb.DuckDBPyConnection,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float,
) -> None:
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, total_distance_km,
            total_time_seconds, avg_pace_seconds_per_km
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [activity_id, activity_date, distance_km, int(distance_km * 300), 300.0],
    )


def _seed_gap_history(db_path: Path) -> None:
    """Seed two pre-gap runs (Sunday=4 km, Monday=6 km), a gap, then recent runs.

    Under Monday-start weeks the Sunday and Monday runs fall in *different*
    calendar weeks (volumes 4 and 6 -> median 5.0). Under Sunday-start weeks
    they share one week (volume 10 -> median 10.0).
    """
    today = datetime.now().date()
    anchor = today - timedelta(days=30)
    sunday = anchor - timedelta(days=(anchor.weekday() - 6) % 7)
    monday = sunday + timedelta(days=1)

    conn = duckdb.connect(str(db_path))
    try:
        _insert_activity(
            conn,
            activity_id=8001,
            activity_date=sunday.strftime("%Y-%m-%d"),
            distance_km=4.0,
        )
        _insert_activity(
            conn,
            activity_id=8002,
            activity_date=monday.strftime("%Y-%m-%d"),
            distance_km=6.0,
        )
        # Post-gap recent runs (creating a >7 day gap before them).
        _insert_activity(
            conn,
            activity_id=8003,
            activity_date=(today - timedelta(days=3)).strftime("%Y-%m-%d"),
            distance_km=5.0,
        )
        _insert_activity(
            conn,
            activity_id=8004,
            activity_date=(today - timedelta(days=1)).strftime("%Y-%m-%d"),
            distance_km=5.0,
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_fitness_default_monday(fitness_db_path: Path) -> None:
    """No profile row -> Monday weeks: Sun/Mon runs are separate weeks (median 5)."""
    _seed_gap_history(fitness_db_path)

    summary = FitnessAssessor(db_path=str(fitness_db_path)).assess(lookback_weeks=8)

    assert summary.gap_detected is True
    # Monday-start weeks split the Sunday (4 km) and Monday (6 km) runs ->
    # weekly volumes [4, 6] -> median 5.0 (matches ISO-week grouping).
    assert summary.pre_gap_weekly_volume_km == 5.0


@pytest.mark.integration
def test_weekly_volume_uses_configured_week(fitness_db_path: Path) -> None:
    """week_start_day=6 -> Sun/Mon runs share one week (median 10)."""
    conn = duckdb.connect(str(fitness_db_path))
    try:
        conn.execute(
            "INSERT INTO athlete_profile (user_id, week_start_day) VALUES (?, ?)",
            ["default", 6],
        )
    finally:
        conn.close()

    _seed_gap_history(fitness_db_path)

    summary = FitnessAssessor(db_path=str(fitness_db_path)).assess(lookback_weeks=8)

    assert summary.gap_detected is True
    # Sunday-start weeks merge the Sunday (4 km) and Monday (6 km) runs into one
    # week -> weekly volume [10] -> median 10.0.
    assert summary.pre_gap_weekly_volume_km == 10.0
