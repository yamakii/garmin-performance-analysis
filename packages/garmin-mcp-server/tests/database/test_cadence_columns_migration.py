"""Test migration that adds pace-dependent cadence columns to form_evaluations."""

import duckdb
import pytest


@pytest.fixture
def tmp_db_path(tmp_path):
    """Create a temporary DuckDB database with legacy form_evaluations schema."""
    db_path = tmp_path / "test_cadence.duckdb"
    conn = duckdb.connect(str(db_path))

    # Legacy form_evaluations with only the old cadence columns
    conn.execute("""
        CREATE TABLE IF NOT EXISTS form_evaluations (
            activity_id INTEGER PRIMARY KEY,
            cadence_actual FLOAT,
            cadence_minimum INTEGER DEFAULT 180,
            cadence_achieved BOOLEAN
        )
        """)
    conn.close()

    from garmin_mcp.database.migrations.add_cadence_columns import (
        migrate_cadence_schema,
    )

    migrate_cadence_schema(str(db_path))
    return str(db_path)


@pytest.mark.integration
def test_migration_adds_cadence_columns(tmp_db_path):
    """All new pace-dependent cadence columns should exist after migration."""
    conn = duckdb.connect(tmp_db_path, read_only=True)
    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()
    column_names = [row[1] for row in schema]
    conn.close()

    expected = [
        "cadence_expected",
        "cadence_delta_pct",
        "cadence_star_rating",
        "cadence_score",
        "cadence_needs_improvement",
        "cadence_evaluation_text",
    ]
    for col in expected:
        assert col in column_names, f"{col} column should exist"

    # Legacy columns retained for backward compatibility
    for legacy in ("cadence_actual", "cadence_minimum", "cadence_achieved"):
        assert legacy in column_names, f"legacy {legacy} should be retained"


@pytest.mark.integration
def test_migration_is_idempotent(tmp_db_path):
    """Running the migration twice should not error (ADD COLUMN IF NOT EXISTS)."""
    from garmin_mcp.database.migrations.add_cadence_columns import (
        migrate_cadence_schema,
    )

    # Second run should be a no-op
    migrate_cadence_schema(tmp_db_path)

    conn = duckdb.connect(tmp_db_path, read_only=True)
    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()
    column_names = [row[1] for row in schema]
    conn.close()

    assert "cadence_expected" in column_names
