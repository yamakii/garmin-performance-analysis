"""Tests for the ``drop_plan_tables`` migration (v17, issue #788, parent #781).

Verifies that the migration drops the self-authored ``training_plans`` and
``planned_workouts`` tables, that it is idempotent (safe on a DB that never had
them), and that it is registered as the current head of ``MIGRATIONS``.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.drop_plan_tables import drop_plan_tables
from garmin_mcp.database.migrations.registry import (
    MIGRATIONS,
    _wrap_drop_plan_tables,
)

_PLAN_TABLES = ("training_plans", "planned_workouts")


def _plan_table_names(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name IN ('training_plans', 'planned_workouts')"
    ).fetchall()
    return sorted(row[0] for row in rows)


@pytest.mark.unit
def test_migration_drops_plan_tables(tmp_path: Path) -> None:
    """Applying to a DB that has the plan tables removes both of them."""
    db_path = tmp_path / "drop.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE training_plans (plan_id VARCHAR)")
        conn.execute("CREATE TABLE planned_workouts (workout_id VARCHAR)")
        assert _plan_table_names(conn) == ["planned_workouts", "training_plans"]

        drop_plan_tables(conn)

        assert _plan_table_names(conn) == []
    finally:
        conn.close()


@pytest.mark.unit
def test_migration_idempotent(tmp_path: Path) -> None:
    """Applying to a DB that never had the tables is a no-op (no exception)."""
    db_path = tmp_path / "drop_idempotent.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        drop_plan_tables(conn)
        # Second application must also be a no-op.
        drop_plan_tables(conn)
        assert _plan_table_names(conn) == []
    finally:
        conn.close()


@pytest.mark.unit
def test_drop_plan_tables_registered_as_v17() -> None:
    """drop_plan_tables is registered at version 17 (no longer the head)."""
    assert (17, "drop_plan_tables", _wrap_drop_plan_tables) in MIGRATIONS
