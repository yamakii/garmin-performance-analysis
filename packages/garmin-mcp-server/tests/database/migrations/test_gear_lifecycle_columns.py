"""Test migration that adds gear lifecycle columns to activities (Issue #1209)."""

import duckdb
import pytest

from garmin_mcp.database.migrations.add_gear_lifecycle_columns import (
    add_gear_lifecycle_columns,
    migrate_gear_lifecycle,
)

_EXPECTED = [
    "gear_max_km",
    "gear_status",
    "gear_since_date",
    "gear_retired_date",
]


@pytest.fixture
def legacy_db_path(tmp_path):
    """An activities table carrying gear identity but no lifecycle columns."""
    db_path = tmp_path / "test_gear_lifecycle.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            gear_model VARCHAR,
            gear_nickname VARCHAR,
            gear_uuid VARCHAR
        )
        """)
    conn.execute(
        "INSERT INTO activities VALUES (1, '2026-09-15', 'NB 1080', 'v15', 'u-v15')"
    )
    conn.close()
    return str(db_path)


@pytest.mark.integration
def test_migration_adds_lifecycle_columns(legacy_db_path):
    migrate_gear_lifecycle(legacy_db_path)

    conn = duckdb.connect(legacy_db_path, read_only=True)
    column_names = [
        row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()
    ]
    conn.close()

    for col in _EXPECTED:
        assert col in column_names, f"{col} column should exist"


@pytest.mark.integration
def test_migration_preserves_existing_rows(legacy_db_path):
    """Identity survives; lifecycle starts null pending the backfill."""
    migrate_gear_lifecycle(legacy_db_path)

    conn = duckdb.connect(legacy_db_path, read_only=True)
    row = conn.execute("""
        SELECT gear_model, gear_nickname, gear_uuid,
               gear_max_km, gear_status, gear_since_date, gear_retired_date
        FROM activities WHERE activity_id = 1
        """).fetchone()
    conn.close()

    assert row == ("NB 1080", "v15", "u-v15", None, None, None, None)


@pytest.mark.integration
def test_migration_is_idempotent(legacy_db_path):
    migrate_gear_lifecycle(legacy_db_path)

    conn = duckdb.connect(legacy_db_path)
    add_gear_lifecycle_columns(conn)
    add_gear_lifecycle_columns(conn)
    column_names = [
        row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()
    ]
    conn.close()

    for col in _EXPECTED:
        assert column_names.count(col) == 1


@pytest.mark.integration
def test_migration_rejects_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        migrate_gear_lifecycle(str(tmp_path / "nope.duckdb"))
