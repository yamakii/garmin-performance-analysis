"""Migration 39: splits.dynamics_suspect (#1635)."""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.splits_dynamics_suspect import (
    add_splits_dynamics_suspect,
)


@pytest.mark.integration
def test_migration_adds_dynamics_suspect(tmp_path: Path) -> None:
    """Existing rows are kept and read FALSE; re-applying is a no-op."""
    conn = duckdb.connect(str(tmp_path / "splits.duckdb"))
    try:
        conn.execute("CREATE TABLE splits (activity_id BIGINT, split_index INTEGER)")
        conn.execute("INSERT INTO splits VALUES (1, 1), (1, 2)")

        add_splits_dynamics_suspect(conn)
        add_splits_dynamics_suspect(conn)

        rows = conn.execute(
            "SELECT split_index, dynamics_suspect FROM splits ORDER BY split_index"
        ).fetchall()
        assert rows == [(1, False), (2, False)]
    finally:
        conn.close()


@pytest.mark.unit
def test_migration_without_splits_table_is_a_noop(tmp_path: Path) -> None:
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    try:
        add_splits_dynamics_suspect(conn)
        assert conn.execute("SHOW TABLES").fetchall() == []
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_version_39() -> None:
    from garmin_mcp.database.migrations.registry import MIGRATIONS

    assert [(v, n) for v, n, _ in MIGRATIONS if v >= 38] == [
        (38, "add_form_baseline_dynamics_source"),
        (39, "add_splits_dynamics_suspect"),
    ]
