"""Tests for the scheduled auto-sync entrypoint (issue #712)."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts import scheduled_sync


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with full schema (base + migrations)."""
    tmp_path = tmp_path_factory.mktemp("sync_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB copy with schema pre-initialized."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path


_ALL_OK = {
    "running": {"activities_ingested": 2},
    "weight": {"days_ingested": 3},
    "strength": {"sessions_ingested": 1},
    "wellness": {"days_ingested": 4},
    "window": {"running": {"start": "2025-10-01", "end": "2025-10-09"}},
}


@pytest.mark.unit
def test_run_sync_records_success(initialized_db_path: Path) -> None:
    """All domains succeed -> one sync_runs row with status 'success'."""
    with patch.object(scheduled_sync, "catch_up_ingest", return_value=dict(_ALL_OK)):
        outcome = scheduled_sync.run_sync(db_path=str(initialized_db_path))

    assert outcome["status"] == "success"
    assert isinstance(outcome["run_id"], int)

    conn = duckdb.connect(str(initialized_db_path), read_only=True)
    rows = conn.execute("SELECT run_id, domains, status FROM sync_runs").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == outcome["run_id"]
    assert rows[0][1] == "running,weight,strength,wellness"
    assert rows[0][2] == "success"


@pytest.mark.unit
def test_run_sync_partial_on_domain_error(initialized_db_path: Path) -> None:
    """A domain error -> status 'partial' and the error persists in results JSON."""
    payload = dict(_ALL_OK)
    payload["wellness"] = {"error": "boom"}

    with patch.object(scheduled_sync, "catch_up_ingest", return_value=payload):
        outcome = scheduled_sync.run_sync(db_path=str(initialized_db_path))

    assert outcome["status"] == "partial"
    assert outcome["results"]["wellness"] == {"error": "boom"}

    conn = duckdb.connect(str(initialized_db_path), read_only=True)
    row = conn.execute("SELECT status, results FROM sync_runs").fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "partial"
    assert "boom" in row[1]


@pytest.mark.unit
def test_run_sync_default_domains_all(initialized_db_path: Path) -> None:
    """domains=None -> catch_up_ingest receives all four default domains."""
    with patch.object(
        scheduled_sync, "catch_up_ingest", return_value=dict(_ALL_OK)
    ) as mock_catch:
        scheduled_sync.run_sync(db_path=str(initialized_db_path))

    mock_catch.assert_called_once()
    assert mock_catch.call_args.kwargs["domains"] == [
        "running",
        "weight",
        "strength",
        "wellness",
    ]


@pytest.mark.unit
def test_main_exit_code_nonzero_on_partial(initialized_db_path: Path) -> None:
    """A partial run -> main() returns exit code 1."""
    payload = dict(_ALL_OK)
    payload["strength"] = {"error": "429"}

    argv = ["prog", "--db-path", str(initialized_db_path)]
    with (
        patch.object(scheduled_sync, "catch_up_ingest", return_value=payload),
        patch("sys.argv", argv),
    ):
        exit_code = scheduled_sync.main()

    assert exit_code == 1


@pytest.mark.integration
def test_sync_runs_migration_creates_table(tmp_path: Path) -> None:
    """Fresh DB gets the sync_runs table via migration; insert/select works."""
    db_path = tmp_path / "fresh.duckdb"
    GarminDBWriter(db_path=str(db_path))

    conn = duckdb.connect(str(db_path))
    run_id_row = conn.execute("SELECT nextval('seq_sync_runs_id')").fetchone()
    assert run_id_row is not None
    run_id = int(run_id_row[0])
    conn.execute(
        """
        INSERT INTO sync_runs (
            run_id, started_at, finished_at, domains, results, status
        ) VALUES (?, now(), now(), ?, ?, ?)
        """,
        [run_id, "running,wellness", '{"running": {}}', "success"],
    )
    rows = conn.execute("SELECT run_id, domains, status FROM sync_runs").fetchall()
    conn.close()

    assert rows == [(run_id, "running,wellness", "success")]
