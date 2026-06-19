"""Integration tests for the body_composition backfill script (#374).

Verifies that backfilling from cached weight JSON is idempotent: the table is
keyed by date, so running the backfill twice does not duplicate rows.
"""

import json
import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts import backfill_body_composition as bbc


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("backfill_bc_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "backfill_bc_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target


def _write_cache(weight_raw_dir: Path, date: str, weight_kg: float) -> None:
    """Write a minimal Garmin weight cache file for a date."""
    weight_raw_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dateWeightList": [
            {
                "calendarDate": date,
                "weight": int(weight_kg * 1000),
                "sourceType": "INDEX_SCALE",
            }
        ]
    }
    with open(weight_raw_dir / f"{date}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f)


@pytest.mark.integration
def test_backfill_body_composition_idempotent(
    db_path: Path, tmp_path: Path, monkeypatch
) -> None:
    """3 cached days → running backfill twice keeps rows == distinct dates == 3."""
    weight_raw_dir = tmp_path / "weight"
    dates = ["2099-05-01", "2099-05-02", "2099-05-03"]
    for i, date in enumerate(dates):
        _write_cache(weight_raw_dir, date, 75.0 + i)
    # An empty marker file must be skipped, not inserted.
    weight_raw_dir.mkdir(parents=True, exist_ok=True)
    with open(weight_raw_dir / "2099-05-04.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    monkeypatch.setattr(bbc, "get_weight_raw_dir", lambda: weight_raw_dir)
    monkeypatch.setattr(bbc, "get_db_path", lambda p: str(db_path))

    first = bbc.backfill_body_composition(db_path=str(db_path))
    second = bbc.backfill_body_composition(db_path=str(db_path))

    assert first["scanned"] == 4
    assert first["inserted"] == 3
    assert first["skipped"] == 1
    assert first["min_date"] == "2099-05-01"
    assert first["max_date"] == "2099-05-03"
    # Idempotent: second run reports the same counts.
    assert second["inserted"] == 3

    conn = duckdb.connect(str(db_path))
    try:
        total = conn.execute("SELECT COUNT(*) FROM body_composition").fetchone()
        distinct = conn.execute(
            "SELECT COUNT(DISTINCT date) FROM body_composition"
        ).fetchone()
    finally:
        conn.close()

    assert total is not None and distinct is not None
    assert total[0] == 3
    assert distinct[0] == 3
