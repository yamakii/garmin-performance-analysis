"""Tests for the ``add_trend_analyses_table`` migration (v16, issue #789).

Verifies that applying the migration creates the ``trend_analyses`` table and
its ``seq_trend_analyses_id`` sequence, that it is idempotent, and that it is
registered as the current head of ``MIGRATIONS``.

Note: the issue design assumed the migration would be v15 (believing the head
was v14 = ``add_sync_runs_table``). The live registry head is actually v15 =
``add_section_analysis_run_id`` (added by #776), so ``trend_analyses`` is v16.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_trend_analyses_table import (
    add_trend_analyses_table,
)
from garmin_mcp.database.migrations.registry import (
    MIGRATIONS,
    _wrap_add_trend_analyses_table,
)


def _table_names(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'trend_analyses'"
    ).fetchall()
    return [row[0] for row in rows]


@pytest.mark.unit
def test_migration_creates_table_and_sequence(tmp_path: Path) -> None:
    """Applying to an empty conn creates an empty table + a sequence at 1."""
    db_path = tmp_path / "trend.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_trend_analyses_table(conn)

        count = conn.execute("SELECT COUNT(*) FROM trend_analyses").fetchone()
        assert count is not None
        assert count[0] == 0

        seq = conn.execute("SELECT nextval('seq_trend_analyses_id')").fetchone()
        assert seq is not None
        assert seq[0] == 1
    finally:
        conn.close()


@pytest.mark.unit
def test_migration_idempotent(tmp_path: Path) -> None:
    """Applying twice does not raise and leaves exactly one table."""
    db_path = tmp_path / "trend_idempotent.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_trend_analyses_table(conn)
        # Second application must be a no-op (no exception).
        add_trend_analyses_table(conn)
        assert _table_names(conn) == ["trend_analyses"]
    finally:
        conn.close()


@pytest.mark.unit
def test_trend_analyses_registered_at_v16() -> None:
    """The trend_analyses migration is registered at version 16."""
    assert (
        16,
        "add_trend_analyses_table",
        _wrap_add_trend_analyses_table,
    ) in MIGRATIONS
