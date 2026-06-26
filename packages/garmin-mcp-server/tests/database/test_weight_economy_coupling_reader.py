"""Integration tests for GarminDBReader.get_weight_economy_coupling (#554).

Builds a tmp DuckDB (schema via ``reader_db_path``), inserts synthetic easy runs
(``activities`` + ``hr_efficiency.training_type='aerobic_base'``), body weights,
and VO2max rows, then asserts the reader couples runs with weight, fits the
longitudinal EF model, and returns the documented shape. Heavier periods are
given a lower EF so the weight coefficient is negative. No real data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_run(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    avg_speed_ms: float,
    avg_heart_rate: int,
    training_type: str = "aerobic_base",
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO activities "
            "(activity_id, activity_date, avg_speed_ms, avg_heart_rate) "
            "VALUES (?, ?, ?, ?)",
            [activity_id, activity_date, avg_speed_ms, avg_heart_rate],
        )
        conn.execute(
            "INSERT INTO hr_efficiency (activity_id, training_type) VALUES (?, ?)",
            [activity_id, training_type],
        )
    finally:
        conn.close()


def _insert_weight(
    db_path: Path, *, measurement_id: int, date: str, weight_kg: float
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO body_composition (measurement_id, date, weight_kg) "
            "VALUES (?, ?, ?)",
            [measurement_id, date, weight_kg],
        )
    finally:
        conn.close()


def _insert_vo2(db_path: Path, *, activity_id: int, value: float, date: str) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO vo2_max (activity_id, value, date) VALUES (?, ?, ?)",
            [activity_id, value, date],
        )
    finally:
        conn.close()


# Weights oscillate in time (decoupled from the day axis); EF is constructed to
# decrease with weight (EF = 0.030 - 0.0005 * (weight - 70)). VO2max varies
# non-collinearly so the design matrix stays full-rank.
_WEIGHTS = [70.0, 73.0, 71.0, 74.0, 70.5, 72.5, 71.5, 73.5, 70.2]
_VO2 = [50.0, 51.2, 50.5, 52.1, 50.1, 51.5, 50.3, 52.3, 50.4]
_HR = 140


def _seed_negative_relationship(db_path: Path) -> None:
    """Seed 9 weekly easy runs where heavier weeks have a lower EF."""
    today = datetime.now()
    for i, (weight, vo2) in enumerate(zip(_WEIGHTS, _VO2, strict=True)):
        d = (today - timedelta(weeks=len(_WEIGHTS) - 1 - i)).strftime("%Y-%m-%d")
        ef = 0.030 - 0.0005 * (weight - 70.0)
        speed = ef * _HR  # EF = speed / HR -> speed = EF * HR
        aid = 5540000 + i
        _insert_run(
            db_path,
            activity_id=aid,
            activity_date=d,
            avg_speed_ms=speed,
            avg_heart_rate=_HR,
        )
        _insert_weight(db_path, measurement_id=i + 1, date=d, weight_kg=weight)
        _insert_vo2(db_path, activity_id=aid, value=vo2, date=d)


@pytest.mark.integration
def test_reader_happy_path_shape(reader_db_path: Path) -> None:
    """Easy runs + body_composition + vo2_max -> documented keys, non-empty
    series, json.dumps-serializable."""
    _seed_negative_relationship(reader_db_path)

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_weight_economy_coupling(weeks=52)

    assert set(result.keys()) >= {
        "weeks",
        "n_runs_total",
        "n_matched",
        "weight_spread_kg",
        "model",
        "series",
        "note",
    }
    assert result["weeks"] == 52
    assert result["n_runs_total"] == len(_WEIGHTS)
    assert result["n_matched"] == len(_WEIGHTS)
    assert result["weight_spread_kg"] > 0
    assert result["model"] is not None
    assert isinstance(result["note"], str) and result["note"]

    assert len(result["series"]) == len(_WEIGHTS)
    for entry in result["series"]:
        assert set(entry.keys()) == {
            "activity_id",
            "run_date",
            "weight_kg",
            "ef",
            "weight_gap_days",
        }
        assert 0.020 <= entry["ef"] <= 0.040
        assert entry["weight_gap_days"] == 0
    # series is run_date-ascending.
    dates = [e["run_date"] for e in result["series"]]
    assert dates == sorted(dates)

    # MCP-boundary serializable.
    json.dumps(result, default=str)


@pytest.mark.integration
def test_reader_returns_negative_weight_coef(reader_db_path: Path) -> None:
    """Heavier periods have a lower EF -> negative weight coef and a positive
    5kg-loss effect size."""
    _seed_negative_relationship(reader_db_path)

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_weight_economy_coupling(weeks=52)

    model = result["model"]
    assert model is not None
    assert model["weight"]["coef"] < 0
    assert model["delta_ef_per_5kg_loss"] > 0


@pytest.mark.integration
def test_reader_insufficient_matches(reader_db_path: Path) -> None:
    """When every weight is >14 days from any run, no run matches: n_matched==0,
    model is None, a reason string is present, and no exception is raised."""
    today = datetime.now()
    # 6 recent easy runs.
    for i in range(6):
        d = (today - timedelta(weeks=5 - i)).strftime("%Y-%m-%d")
        aid = 5541000 + i
        _insert_run(
            reader_db_path,
            activity_id=aid,
            activity_date=d,
            avg_speed_ms=4.1,
            avg_heart_rate=140,
        )
    # Weights are all ~2 years in the past -> always >14 days from the runs.
    for i in range(3):
        d = (today - timedelta(weeks=100 + i)).strftime("%Y-%m-%d")
        _insert_weight(reader_db_path, measurement_id=i + 1, date=d, weight_kg=72.0)

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_weight_economy_coupling(weeks=200)

    assert result["n_matched"] == 0
    assert result["model"] is None
    assert "reason" in result
    assert isinstance(result["reason"], str) and result["reason"]
    assert result["series"] == []
    json.dumps(result, default=str)
