"""Tests for body_composition table backfill / date-keyed upsert (#374).

Covers:
- ``_body_comp_row`` gram→kg conversion and empty-list handling (unit).
- date-keyed dedup via ``insert_body_composition`` (unit).
"""

import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter, _body_comp_row


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with schema pre-initialized."""
    tmp_path = tmp_path_factory.mktemp("body_comp_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB with schema pre-initialized via file copy."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


@pytest.mark.unit
def test_body_comp_row_grams_to_kg() -> None:
    """weight/muscleMass grams convert to kg; empty dateWeightList → None."""
    weight_data = {
        "dateWeightList": [
            {
                "weight": 80199,  # grams → 80.199 kg
                "muscleMass": 31799,  # grams → 31.799 kg
                "boneMass": 3250,  # grams → 3.25 kg
                "bmi": 24.1,
                "bodyFat": 18.5,
                "bodyWater": 55.2,
                "sourceType": "INDEX_SCALE",
            }
        ]
    }

    row = _body_comp_row("2099-01-01", weight_data)

    assert row is not None
    assert abs(row["weight_kg"] - 80.199) < 1e-6
    assert abs(row["muscle_mass_kg"] - 31.799) < 1e-6
    assert abs(row["bone_mass_kg"] - 3.25) < 1e-6
    assert row["bmi"] == 24.1
    assert row["body_fat_percentage"] == 18.5
    assert row["hydration_percentage"] == 55.2
    assert row["measurement_source"] == "INDEX_SCALE"
    assert row["date"] == "2099-01-01"

    # Empty dateWeightList yields None.
    assert _body_comp_row("2099-01-01", {"dateWeightList": []}) is None
    assert _body_comp_row("2099-01-01", {}) is None


@pytest.mark.unit
def test_insert_body_composition_dedups_by_date(initialized_db_path: Path) -> None:
    """Inserting the same date twice keeps 1 row and replaces with latest value."""
    writer = GarminDBWriter(db_path=str(initialized_db_path))
    date = "2099-02-02"

    first = {"dateWeightList": [{"weight": 70000, "sourceType": "INDEX_SCALE"}]}
    second = {"dateWeightList": [{"weight": 71500, "sourceType": "INDEX_SCALE"}]}

    assert writer.insert_body_composition(date, first) is True
    assert writer.insert_body_composition(date, second) is True

    conn = duckdb.connect(str(initialized_db_path))
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM body_composition WHERE date = ?", [date]
        ).fetchone()
        weight_row = conn.execute(
            "SELECT weight_kg FROM body_composition WHERE date = ?", [date]
        ).fetchone()
    finally:
        conn.close()

    assert count_row is not None and weight_row is not None
    assert count_row[0] == 1
    assert abs(weight_row[0] - 71.5) < 1e-6  # replaced with second value
