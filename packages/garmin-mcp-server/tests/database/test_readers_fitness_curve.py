"""Integration tests for FitnessCurveReader (objective fitness curve).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture) and
inserts activities + per-km splits (km-unit distance) plus optional ``vo2_max``
rows, then asserts the objective curve / Garmin optimism gap. No real data.

The km->m conversion is exercised on purpose: splits are inserted in DuckDB's
km unit (``distance == 1.0`` for a 1 km lap), and a non-empty ``objective_curve``
assertion guards against the #565 regression (feeding km straight into the
meter-expecting best-effort helper yields an empty curve).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.readers.fitness_curve import FitnessCurveReader
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch


def _insert_run(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    split_seconds: float,
    n_splits: int = 6,
) -> None:
    """Insert one activity + ``n_splits`` 1 km laps at a constant pace.

    ``distance`` is written in **km** (1.0 per lap), matching the DuckDB unit.
    """
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
        for i in range(n_splits):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds
                ) VALUES (?, ?, ?, ?)
                """,
                [activity_id, i, 1.0, split_seconds],
            )
    finally:
        conn.close()


def _insert_vo2max(db_path: Path, *, activity_id: int, value: float, date: str) -> None:
    """Insert one ``vo2_max`` row."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO vo2_max (activity_id, precise_value, value, date, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            [activity_id, value, value, date, 0],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_objective_fitness_curve_structure(reader_db_path: Path) -> None:
    """Two activities (with splits) + a vo2_max row -> populated structure."""
    _insert_run(
        reader_db_path,
        activity_id=1,
        activity_date="2025-09-01",
        split_seconds=340.0,
    )
    _insert_run(
        reader_db_path,
        activity_id=2,
        activity_date="2025-09-20",
        split_seconds=330.0,
    )
    _insert_vo2max(reader_db_path, activity_id=2, value=44.6, date="2025-09-20")

    reader = FitnessCurveReader(str(reader_db_path))
    result = reader.get_objective_fitness_curve(window_days=90)

    assert set(result) >= {"objective_curve", "garmin_vo2max", "optimism_gap"}
    assert result["objective_curve"], "objective_curve must be non-empty"
    for point in result["objective_curve"]:
        assert {"date", "vdot", "source_distance_km"} <= set(point)
        assert 20.0 <= point["vdot"] <= 45.0
    assert result["garmin_vo2max"] == [{"date": "2025-09-20", "value": 44.6}]


@pytest.mark.integration
def test_get_objective_fitness_curve_optimism_gap_positive(
    reader_db_path: Path,
) -> None:
    """Garmin VO2max 44.6 vs objective ~33 -> positive gap, pace gap 40-90 s/km."""
    _insert_run(
        reader_db_path,
        activity_id=1,
        activity_date="2025-10-01",
        split_seconds=340.0,
    )
    _insert_vo2max(reader_db_path, activity_id=1, value=44.6, date="2025-10-01")

    reader = FitnessCurveReader(str(reader_db_path))
    result = reader.get_objective_fitness_curve(window_days=90)

    gap = result["optimism_gap"]
    assert gap is not None
    assert gap["gap_vdot"] > 0
    assert 40.0 <= gap["gap_pace_sec_per_km"] <= 90.0
    assert gap["garmin_vdot"] > gap["objective_vdot"]


@pytest.mark.integration
def test_get_objective_fitness_curve_empty_db(reader_db_path: Path) -> None:
    """No splits and no vo2_max -> empty curve, no exception."""
    reader = FitnessCurveReader(str(reader_db_path))
    result = reader.get_objective_fitness_curve(window_days=90)

    assert result["objective_curve"] == []
    assert result["garmin_vo2max"] == []
    assert result["optimism_gap"] is None


@pytest.mark.integration
def test_e2e_objective_fitness_dispatch(reader_db_path: Path) -> None:
    """dispatch(...) at the MCP boundary returns a json.dumps-able dict."""
    _insert_run(
        reader_db_path,
        activity_id=1,
        activity_date="2025-10-01",
        split_seconds=340.0,
    )
    _insert_vo2max(reader_db_path, activity_id=1, value=44.6, date="2025-10-01")

    reader = GarminDBReader(str(reader_db_path))
    result = dispatch(
        ALL_DEFS_BY_NAME,
        reader,
        "get_objective_fitness_curve",
        {"window_days": 90},
    )

    assert isinstance(result, dict)
    # Serializable across the MCP boundary.
    encoded = json.dumps(result, default=str)
    assert "objective_curve" in json.loads(encoded)
