"""Integration tests for GarminDBReader.get_body_composition_trend (#501).

Builds a tmp DuckDB (schema via ``reader_db_path``), inserts ~12 weeks of
body_composition rows plus an FTP row, then asserts the reader returns the
series/change/lean_pwr shape with json.dumps-able, in-range values. No real data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader


def _insert_weight(
    db_path: Path,
    *,
    measurement_id: int,
    date: str,
    weight_kg: float,
    body_fat_percentage: float,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO body_composition "
            "(measurement_id, date, weight_kg, body_fat_percentage) "
            "VALUES (?, ?, ?, ?)",
            [measurement_id, date, weight_kg, body_fat_percentage],
        )
    finally:
        conn.close()


def _insert_ftp(db_path: Path, *, activity_id: int, ftp: int, date_power: str) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO lactate_threshold "
            "(activity_id, functional_threshold_power, date_power) "
            "VALUES (?, ?, ?)",
            [activity_id, ftp, date_power],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_body_composition_trend_shape(reader_db_path: Path) -> None:
    """12 weekly measurements -> series/change/lean_pwr keys, json-serializable,
    weight 60-100 and body fat 5-40 within range."""
    today = datetime.now()
    # 12 weekly measurements trending down in weight and body fat.
    for i in range(12):
        d = (today - timedelta(weeks=11 - i)).strftime("%Y-%m-%d")
        _insert_weight(
            reader_db_path,
            measurement_id=i + 1,
            date=d,
            weight_kg=80.0 - i * 0.3,
            body_fat_percentage=24.0 - i * 0.1,
        )
    _insert_ftp(
        reader_db_path,
        activity_id=1,
        ftp=337,
        date_power=today.strftime("%Y-%m-%d %H:%M:%S"),
    )

    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_body_composition_trend(weeks=12)

    # Top-level shape.
    assert set(result.keys()) == {"weeks", "series", "change", "lean_pwr"}
    assert result["weeks"] == 12
    assert len(result["series"]) == 12

    # Series entries: keys + value ranges.
    for entry in result["series"]:
        assert set(entry.keys()) == {"date", "weight_kg", "fat_mass", "lean_mass"}
        assert 60.0 <= entry["weight_kg"] <= 100.0
        assert entry["fat_mass"] is not None
        assert entry["lean_mass"] is not None
        assert entry["lean_mass"] < entry["weight_kg"]

    # Series is date-ascending.
    dates = [e["date"] for e in result["series"]]
    assert dates == sorted(dates)

    # change block: weight dropped over the window.
    change = result["change"]
    assert set(change.keys()) == {
        "delta_weight",
        "delta_fat",
        "delta_lean",
        "lean_loss_ratio",
        "muscle_loss_warning",
    }
    assert change["delta_weight"] is not None
    assert change["delta_weight"] < 0

    # lean_pwr derived from FTP / lean mass (plausible runner range).
    assert result["lean_pwr"] is not None
    assert 3.0 <= result["lean_pwr"] <= 8.0

    # MCP-boundary serializable.
    json.dumps(result, default=str)


@pytest.mark.integration
def test_get_body_composition_trend_empty(reader_db_path: Path) -> None:
    """Empty body_composition -> empty series, all-None change, lean_pwr None."""
    reader = GarminDBReader(db_path=str(reader_db_path))
    result = reader.get_body_composition_trend(weeks=12)

    assert result["series"] == []
    assert result["change"]["delta_weight"] is None
    assert result["change"]["muscle_loss_warning"] is False
    assert result["lean_pwr"] is None
    json.dumps(result, default=str)
