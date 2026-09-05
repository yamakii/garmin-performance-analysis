"""Tests for migration v23 (add_training_blocks_tables).

Verifies that applying v23 creates the mesocycle ledger tables and their
sequences, that re-applying it is a no-op, and that the registry exposes the two
new migrations last and in order.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_training_blocks_tables import (
    add_training_blocks_tables,
)
from garmin_mcp.database.migrations.registry import MIGRATIONS

BLOCK_TABLES = {"training_blocks", "training_block_versions"}
BLOCK_SEQUENCES = {"seq_training_blocks_id", "seq_training_block_versions_id"}


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {row[0] for row in rows}


def _sequence_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT sequence_name FROM duckdb_sequences()").fetchall()
    return {row[0] for row in rows}


@pytest.mark.unit
def test_add_training_blocks_tables_creates_tables_and_sequences(
    tmp_path: Path,
) -> None:
    """v23 creates both tables + sequences, and applying it twice is idempotent."""
    conn = duckdb.connect(str(tmp_path / "blocks.duckdb"))
    try:
        add_training_blocks_tables(conn)
        assert BLOCK_TABLES.issubset(_table_names(conn))
        assert BLOCK_SEQUENCES.issubset(_sequence_names(conn))

        # Second application must be a no-op (no exception, tables intact).
        add_training_blocks_tables(conn)
        assert BLOCK_TABLES.issubset(_table_names(conn))

        conn.execute(
            "INSERT INTO training_blocks "
            "(block_id, user_id, sequence, phase, title, start_date, end_date) "
            "VALUES (nextval('seq_training_blocks_id'), 'default', 1, 'build', "
            "'新潟ラダー', DATE '2026-08-24', DATE '2026-09-20')"
        )
        row = conn.execute(
            "SELECT block_id, phase, title FROM training_blocks"
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "build"
        assert row[2] == "新潟ラダー"
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_versions_23_and_24_in_order() -> None:
    """The two plan-storage migrations are appended last, 23 then 24."""
    assert [(version, name) for version, name, _ in MIGRATIONS[-2:]] == [
        (23, "add_training_blocks_tables"),
        (24, "add_weekly_prescriptions_table"),
    ]
