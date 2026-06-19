"""Integration tests for DB-sourced 7-day median weight (#374).

``_calculate_median_weight`` now treats the ``body_composition`` table as the
single source of truth:
- cached weight JSON within the 7-day window is upserted into the table, then
- the window is read back and median-aggregated per column.
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with schema pre-initialized."""
    tmp_path = tmp_path_factory.mktemp("median_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB with schema pre-initialized via file copy."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


@pytest.fixture
def worker(tmp_path, monkeypatch, initialized_db_path):
    """Worker with temp dirs and a pre-initialized DuckDB path."""
    monkeypatch.setattr("garmin_mcp.utils.paths.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_raw_dir",
        lambda: tmp_path / "data" / "raw",
    )
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_weight_raw_dir",
        lambda: tmp_path / "data" / "raw" / "weight",
    )
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_default_db_path",
        lambda: str(initialized_db_path),
    )
    monkeypatch.setattr(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        Mock(side_effect=ValueError("No credentials in test")),
    )

    w = GarminIngestWorker(db_path=str(initialized_db_path))
    w._ensure_dirs()
    return w


def _seed_body_composition(db_path: Path, rows: list[tuple[str, float]]) -> None:
    """Insert (date, weight_kg) rows directly into body_composition."""
    conn = duckdb.connect(str(db_path))
    try:
        for i, (date, weight_kg) in enumerate(rows, start=1):
            conn.execute(
                "INSERT INTO body_composition (measurement_id, date, weight_kg) "
                "VALUES (?, ?, ?)",
                [i, date, weight_kg],
            )
    finally:
        conn.close()


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
def test_calculate_median_weight_reads_from_db(worker, initialized_db_path) -> None:
    """7 days seeded ([76.0..76.6]) → median≈76.3, source/sample_count intact."""
    target = "2099-03-10"
    target_dt = datetime.strptime(target, "%Y-%m-%d")
    rows = [
        ((target_dt - timedelta(days=i)).strftime("%Y-%m-%d"), 76.0 + i * 0.1)
        for i in range(7)
    ]
    _seed_body_composition(initialized_db_path, rows)

    # No cache files: nothing to sync, table is read directly.
    result = worker._calculate_median_weight(target)

    assert result is not None
    assert abs(result["weight_kg"] - 76.3) < 0.01
    assert result["source"] == "7DAY_MEDIAN"
    assert result["sample_count"] == 7
    assert result["date"] == target


@pytest.mark.integration
def test_calculate_median_weight_syncs_cache_window(
    worker, initialized_db_path
) -> None:
    """Empty table + 3 cached days in window → table gets 3 rows & median computed."""
    target = "2099-04-10"
    target_dt = datetime.strptime(target, "%Y-%m-%d")
    cache_dates = [
        ((target_dt - timedelta(days=i)).strftime("%Y-%m-%d"), 80.0 + i)
        for i in (0, 2, 5)  # weights 80.0, 82.0, 85.0 within the 7-day window
    ]
    for date, weight_kg in cache_dates:
        _write_cache(worker.weight_raw_dir, date, weight_kg)

    result = worker._calculate_median_weight(target)

    # Median of [80.0, 82.0, 85.0] = 82.0
    assert result is not None
    assert abs(result["weight_kg"] - 82.0) < 0.01
    assert result["sample_count"] == 3

    # Cache → table sync: exactly 3 rows landed in the table.
    conn = duckdb.connect(str(initialized_db_path))
    try:
        count_row = conn.execute("SELECT COUNT(*) FROM body_composition").fetchone()
    finally:
        conn.close()
    assert count_row is not None
    assert count_row[0] == 3
