"""Tests for the athlete_symptoms table migration (Issue #1220)."""

from __future__ import annotations

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.migrations.add_athlete_symptoms import add_athlete_symptoms
from garmin_mcp.database.migrations.registry import MIGRATIONS

_EXPECTED_COLUMNS = [
    "symptom_id",
    "user_id",
    "date",
    "body_region",
    "side",
    "severity",
    "phase",
    "activity_id",
    "note",
    "created_at",
]


@pytest.mark.unit
def test_migration_creates_table_and_is_idempotent() -> None:
    """Running the migration twice leaves exactly one well-formed table."""
    conn = duckdb.connect(":memory:")
    try:
        add_athlete_symptoms(conn)
        add_athlete_symptoms(conn)

        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(athlete_symptoms)").fetchall()
        ]
        assert columns == _EXPECTED_COLUMNS

        # The sequence backs the PK default, so an insert without an id works.
        conn.execute(
            "INSERT INTO athlete_symptoms (date, body_region, severity, phase) "
            "VALUES ('2026-09-18', 'calf', 3, 'morning')"
        )
        row = conn.execute(
            "SELECT symptom_id, user_id FROM athlete_symptoms"
        ).fetchone()
        assert row == (1, "default")
    finally:
        conn.close()


@pytest.mark.unit
def test_registry_has_version_29() -> None:
    """The symptom log is registered as migration 29, after the gear columns."""
    assert [
        (version, name) for version, name, _ in MIGRATIONS if 28 <= version <= 29
    ] == [
        (28, "add_gear_lifecycle_columns"),
        (29, "add_athlete_symptoms"),
    ]


@pytest.mark.integration
def test_ensure_tables_creates_athlete_symptoms(memory_db_path: str) -> None:
    """A freshly constructed writer already has the table (no migration needed)."""
    GarminDBWriter(db_path=memory_db_path)  # real DDL: this is a schema check

    conn = duckdb.connect(memory_db_path)
    try:
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(athlete_symptoms)").fetchall()
        ]
    finally:
        conn.close()

    assert columns == _EXPECTED_COLUMNS
