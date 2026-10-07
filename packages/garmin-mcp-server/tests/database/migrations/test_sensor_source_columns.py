"""Test migration that adds sensor source columns to activities (Issue #1459)."""

import duckdb
import pytest

from garmin_mcp.database.migrations.add_sensor_source_columns import (
    add_sensor_source_columns,
)
from garmin_mcp.database.migrations.registry import MIGRATIONS


@pytest.mark.unit
def test_registry_has_version_35() -> None:
    """The sensor source columns are registered as migration 35, the schema head."""
    assert (35, "add_sensor_source_columns") in [
        (version, name) for version, name, _ in MIGRATIONS
    ]
    assert max(version for version, _, _ in MIGRATIONS) == 35


@pytest.mark.integration
def test_add_sensor_source_columns_idempotent(tmp_path):
    conn = duckdb.connect(str(tmp_path / "test_sensor_source.duckdb"))
    conn.execute("""
        CREATE TABLE activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE
        )
        """)
    conn.execute("INSERT INTO activities VALUES (1, '2026-10-07')")

    add_sensor_source_columns(conn)
    add_sensor_source_columns(conn)

    column_names = [
        row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()
    ]
    row = conn.execute(
        "SELECT dynamics_source, hr_source FROM activities WHERE activity_id = 1"
    ).fetchone()
    conn.close()

    assert column_names.count("dynamics_source") == 1
    assert column_names.count("hr_source") == 1
    assert row == (None, None)
