"""Tests for migration v21 (add_athlete_profile_versions).

Verifies that applying v21 creates the append-only snapshot table + sequence,
seeds the profile that exists at migration time as the first version, and stays
idempotent when applied again.
"""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.add_athlete_profile_versions import (
    add_athlete_profile_versions,
)
from garmin_mcp.database.migrations.add_athlete_tables import add_athlete_tables
from garmin_mcp.database.migrations.registry import (
    MIGRATIONS,
    _wrap_add_athlete_profile_versions,
)


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {row[0] for row in rows}


def _sequence_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT sequence_name FROM duckdb_sequences()").fetchall()
    return {row[0] for row in rows}


@pytest.mark.unit
def test_migration_creates_profile_versions_table(tmp_path: Path) -> None:
    """v21 creates athlete_profile_versions and its id sequence."""
    db_path = tmp_path / "profile_versions.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        add_athlete_profile_versions(conn)

        tables = _table_names(conn)
        sequences = _sequence_names(conn)
    finally:
        conn.close()

    assert "athlete_profile_versions" in tables
    assert "seq_athlete_profile_versions_id" in sequences


@pytest.mark.unit
def test_migration_seeds_existing_profile_as_first_version(tmp_path: Path) -> None:
    """The profile present at migration time becomes version 1 (idempotently)."""
    db_path = tmp_path / "profile_versions_seed.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        conn.execute(
            "INSERT INTO athlete_profile "
            "(user_id, current_focus, focus_notes, week_start_day) "
            "VALUES ('default', '脚の耐久性', 'old', 0)"
        )
        conn.execute(
            "INSERT INTO athlete_goals "
            "(goal_id, user_id, race_name, race_date, priority, goal_type) "
            "VALUES (nextval('seq_athlete_goals_id'), 'default', "
            "'新潟シティマラソン', DATE '2026-10-11', 'A', 'marathon')"
        )

        add_athlete_profile_versions(conn)

        rows = conn.execute(
            "SELECT version_id, user_id, profile_data "
            "FROM athlete_profile_versions ORDER BY version_id"
        ).fetchall()
        assert len(rows) == 1
        snapshot = json.loads(rows[0][2])
        assert rows[0][1] == "default"
        assert snapshot["focus_notes"] == "old"
        assert snapshot["current_focus"] == "脚の耐久性"
        assert len(snapshot["goals"]) == 1
        assert snapshot["goals"][0]["race_name"] == "新潟シティマラソン"
        assert snapshot["goals"][0]["race_date"] == "2026-10-11"
        assert snapshot["retrospectives"] == []

        # Re-applying must not seed a second copy.
        add_athlete_profile_versions(conn)
        count_row = conn.execute(
            "SELECT COUNT(*) FROM athlete_profile_versions"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == 1
    finally:
        conn.close()


@pytest.mark.unit
def test_migration_registered_as_v21() -> None:
    """add_athlete_profile_versions is registered at version 21."""
    assert (
        21,
        "add_athlete_profile_versions",
        _wrap_add_athlete_profile_versions,
    ) in MIGRATIONS


@pytest.mark.unit
def test_migration_without_athlete_profile_table(tmp_path: Path) -> None:
    """Seeding is skipped (no error) when athlete_profile does not exist yet."""
    db_path = tmp_path / "profile_versions_bare.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_profile_versions(conn)
        count_row = conn.execute(
            "SELECT COUNT(*) FROM athlete_profile_versions"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == 0
    finally:
        conn.close()
