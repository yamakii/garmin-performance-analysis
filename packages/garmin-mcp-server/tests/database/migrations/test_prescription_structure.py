"""Tests for migration v33: weekly_prescriptions.structure (Issue #1401).

The step structure of a prescription is stored as JSON in a nullable VARCHAR,
following the ``strides`` (v30) and ``purpose`` / ``allowances`` (v32)
precedent. Rows written before the migration stay NULL.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_prescription_purpose import (
    add_prescription_purpose,
)
from garmin_mcp.database.migrations.add_prescription_structure import (
    migrate_add_prescription_structure,
)
from garmin_mcp.database.migrations.add_weekly_prescriptions_table import (
    add_weekly_prescriptions_table,
)


def _structure_columns(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'weekly_prescriptions' AND column_name = 'structure'"
    ).fetchall()


@pytest.mark.integration
def test_migration_v33_adds_structure_column(tmp_path: Path) -> None:
    """A v32 DB gains a nullable structure VARCHAR; a second run is a no-op."""
    conn = duckdb.connect(str(tmp_path / "structure.duckdb"))
    try:
        # A v32-shaped table with one existing row.
        add_weekly_prescriptions_table(conn)
        add_prescription_purpose(conn)
        conn.execute(
            "INSERT INTO weekly_prescriptions (prescription_id, batch_id, "
            "week_start_date, date, session_type, title) VALUES "
            "(1, 1, DATE '2026-09-07', DATE '2026-09-09', 'easy', 'easy')"
        )
        assert _structure_columns(conn) == []

        migrate_add_prescription_structure(conn)
        assert _structure_columns(conn) == [("structure", "VARCHAR")]

        # Idempotent: a second application must not raise or change anything.
        migrate_add_prescription_structure(conn)
        assert _structure_columns(conn) == [("structure", "VARCHAR")]

        stored = conn.execute(
            "SELECT structure FROM weekly_prescriptions WHERE prescription_id = 1"
        ).fetchone()
        assert stored == (None,)
    finally:
        conn.close()


@pytest.mark.unit
def test_migration_v33_without_table_is_noop(tmp_path: Path) -> None:
    """Without weekly_prescriptions there is nothing to alter and no crash."""
    conn = duckdb.connect(str(tmp_path / "no_table.duckdb"))
    try:
        migrate_add_prescription_structure(conn)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
        assert ("weekly_prescriptions",) not in tables
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_version_33() -> None:
    """The structure column is registered as migration 33, after purpose."""
    from garmin_mcp.database.migrations.registry import MIGRATIONS

    assert [(version, name) for version, name, _ in MIGRATIONS if version >= 32] == [
        (32, "add_prescription_purpose"),
        (33, "add_prescription_structure"),
    ]
