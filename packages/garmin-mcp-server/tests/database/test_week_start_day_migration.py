"""Integration tests for migration v12 (add_week_start_day) + reader/inserter.

Verifies that the migration adds ``athlete_profile.week_start_day`` (existing
rows defaulting to 0), is idempotent, and that the column round-trips through
the athlete inserter/reader.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.athlete import insert_athlete_profile
from garmin_mcp.database.migrations.add_athlete_tables import add_athlete_tables
from garmin_mcp.database.migrations.add_week_start_day import add_week_start_day
from garmin_mcp.database.readers.athlete import AthleteReader


def _column_names(conn: duckdb.DuckDBPyConnection) -> list[str]:
    schema = conn.execute("PRAGMA table_info(athlete_profile)").fetchall()
    return [row[1] for row in schema]


@pytest.mark.integration
def test_migration_adds_column(tmp_path: Path) -> None:
    """v12 adds week_start_day; a pre-existing row defaults to 0."""
    db_path = tmp_path / "week_start.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        # Simulate a legacy DB at v7: athlete tables without week_start_day.
        conn.execute("""
            CREATE TABLE athlete_profile (
                user_id VARCHAR PRIMARY KEY DEFAULT 'default',
                current_focus VARCHAR,
                focus_notes VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO athlete_profile (user_id, current_focus) "
            "VALUES ('default', 'BASE')"
        )

        add_week_start_day(conn)

        assert "week_start_day" in _column_names(conn)
        row = conn.execute(
            "SELECT week_start_day FROM athlete_profile WHERE user_id = 'default'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0
    finally:
        conn.close()


@pytest.mark.integration
def test_migration_idempotent(tmp_path: Path) -> None:
    """Applying v12 twice does not raise and the column persists once."""
    db_path = tmp_path / "week_start_idempotent.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        add_athlete_tables(conn)
        add_week_start_day(conn)
        # Second application must be a no-op (no exception, no duplicate column).
        add_week_start_day(conn)

        assert _column_names(conn).count("week_start_day") == 1
    finally:
        conn.close()


@pytest.mark.integration
def test_save_and_get_week_start_day(tmp_path: Path) -> None:
    """Saving a profile with week_start_day=6 reads back as 6."""
    db_path = str(tmp_path / "save_get.duckdb")
    GarminDBWriter(db_path=db_path)  # runs migrations incl. v12

    insert_athlete_profile(
        {"user_id": "default", "current_focus": "BASE", "week_start_day": 6},
        db_path=db_path,
    )

    result = AthleteReader(db_path=db_path).get_athlete_profile()
    assert result["week_start_day"] == 6


@pytest.mark.integration
def test_get_profile_default_when_unset(tmp_path: Path) -> None:
    """A saved profile that omits week_start_day reads back as 0 (default)."""
    db_path = str(tmp_path / "default_unset.duckdb")
    GarminDBWriter(db_path=db_path)

    insert_athlete_profile(
        {"user_id": "default", "current_focus": "BASE"},
        db_path=db_path,
    )

    result = AthleteReader(db_path=db_path).get_athlete_profile()
    assert result["week_start_day"] == 0
