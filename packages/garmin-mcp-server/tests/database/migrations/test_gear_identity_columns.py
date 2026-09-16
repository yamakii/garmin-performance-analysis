"""Test migration that adds gear identity columns to activities (Issue #1207)."""

import duckdb
import pytest

from garmin_mcp.database.migrations.add_gear_identity_columns import (
    add_gear_identity_columns,
    migrate_gear_identity,
)


@pytest.fixture
def legacy_db_path(tmp_path):
    """A DB whose activities table predates gear_nickname / gear_uuid."""
    db_path = tmp_path / "test_gear_identity.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            gear_type VARCHAR,
            gear_model VARCHAR
        )
        """)
    conn.execute("INSERT INTO activities VALUES (1, '2026-09-06', 'Shoes', 'NB 1080')")
    conn.close()
    return str(db_path)


@pytest.mark.integration
def test_migration_adds_gear_identity_columns(legacy_db_path):
    """gear_nickname and gear_uuid exist after the migration."""
    migrate_gear_identity(legacy_db_path)

    conn = duckdb.connect(legacy_db_path, read_only=True)
    schema = conn.execute("PRAGMA table_info(activities)").fetchall()
    conn.close()

    column_names = [row[1] for row in schema]
    assert "gear_nickname" in column_names
    assert "gear_uuid" in column_names


@pytest.mark.integration
def test_migration_preserves_existing_rows(legacy_db_path):
    """Existing gear survives; the new columns start null pending a re-ingest."""
    migrate_gear_identity(legacy_db_path)

    conn = duckdb.connect(legacy_db_path, read_only=True)
    row = conn.execute("""
        SELECT gear_type, gear_model, gear_nickname, gear_uuid
        FROM activities WHERE activity_id = 1
        """).fetchone()
    conn.close()

    assert row == ("Shoes", "NB 1080", None, None)


@pytest.mark.integration
def test_migration_is_idempotent(legacy_db_path):
    """Re-running the migration is a no-op, not an error."""
    migrate_gear_identity(legacy_db_path)

    conn = duckdb.connect(legacy_db_path)
    add_gear_identity_columns(conn)
    add_gear_identity_columns(conn)
    schema = conn.execute("PRAGMA table_info(activities)").fetchall()
    conn.close()

    column_names = [row[1] for row in schema]
    assert column_names.count("gear_nickname") == 1
    assert column_names.count("gear_uuid") == 1


@pytest.mark.integration
def test_migration_rejects_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        migrate_gear_identity(str(tmp_path / "nope.duckdb"))
