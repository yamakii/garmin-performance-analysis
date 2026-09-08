"""In-memory DuckDB paths through the connection helpers (#1062)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.connection import (
    get_connection,
    get_write_connection,
    is_memory_db_path,
)
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.migrations.backup import backup_if_pending


@pytest.mark.unit
@pytest.mark.parametrize(
    ("db_path", "expected"),
    [
        (":memory:", True),
        (":memory:abc", True),
        (Path(":memory:abc"), True),
        ("/tmp/x.duckdb", False),
        (Path("relative.duckdb"), False),
        (None, False),
    ],
)
def test_is_memory_db_path(db_path: str | Path | None, expected: bool) -> None:
    assert is_memory_db_path(db_path) is expected


@pytest.mark.unit
def test_memory_path_shared_between_writer_and_reader(memory_db_path: str) -> None:
    """The writer's DDL (real GarminDBWriter) is visible to a later connection."""
    GarminDBWriter(db_path=memory_db_path)

    with get_connection(memory_db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
    assert "activities" in tables
    assert "schema_version" in tables


@pytest.mark.unit
def test_memory_path_ignores_read_only(memory_db_path: str) -> None:
    """get_connection (read-only elsewhere) must not raise on a memory name."""
    with get_write_connection(memory_db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")

    with get_connection(memory_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone() == (1,)


@pytest.mark.unit
def test_memory_paths_are_isolated_per_name() -> None:
    """Two names are two databases; a name without an anchor starts empty."""
    a = duckdb.connect(":memory:isolated_a")
    b = duckdb.connect(":memory:isolated_b")
    try:
        a.execute("CREATE TABLE only_a (x INTEGER)")
        assert b.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'only_a'"
        ).fetchone() == (0,)
    finally:
        a.close()
        b.close()


@pytest.mark.unit
def test_backup_skips_memory_path(memory_db_path: str, tmp_path: Path) -> None:
    """backup_if_pending returns None for a memory name and writes nothing."""
    before = sorted(tmp_path.iterdir())
    assert backup_if_pending(memory_db_path) is None
    assert sorted(tmp_path.iterdir()) == before
