"""Migration 31: splits.workout_step_index (#1296)."""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_splits_workout_step_index import (
    add_splits_workout_step_index,
)


@pytest.mark.unit
def test_add_splits_workout_step_index_idempotent(tmp_path: Path) -> None:
    """v31 adds one nullable INTEGER column; re-applying is a no-op."""
    conn = duckdb.connect(str(tmp_path / "splits.duckdb"))
    try:
        conn.execute("CREATE TABLE splits (activity_id BIGINT, split_index INTEGER)")
        add_splits_workout_step_index(conn)
        add_splits_workout_step_index(conn)

        columns = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'splits' AND column_name = 'workout_step_index'"
        ).fetchall()
        assert columns == [("workout_step_index", "INTEGER")]
    finally:
        conn.close()


@pytest.mark.unit
def test_add_splits_workout_step_index_missing_table(tmp_path: Path) -> None:
    """Without a splits table the migration does nothing and does not raise."""
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    try:
        add_splits_workout_step_index(conn)
        tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
        assert "splits" not in tables
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_version_31() -> None:
    """The step-index column is migration 31, after the strides add-on."""
    from garmin_mcp.database.migrations.registry import MIGRATIONS

    assert [
        (version, name) for version, name, _ in MIGRATIONS if 30 <= version <= 31
    ] == [
        (30, "add_prescription_strides"),
        (31, "add_splits_workout_step_index"),
    ]
