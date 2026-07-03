"""Integration tests for the worker startup migration hook (issue #631).

The MCP worker applies pending schema migrations once at startup so that
read-only tools (which never construct ``GarminDBWriter``) observe an
up-to-date schema instead of crashing on a column a newer reader expects.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp import worker
from garmin_mcp.database.migrations.runner import MigrationRunner
from garmin_mcp.database.readers.athlete import AthleteReader


def _create_schema_only_db(db_path: Path) -> None:
    """Create a DB with the base tables but no migrations applied."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    writer = object.__new__(GarminDBWriter)
    writer.db_path = db_path
    writer._ensure_tables()


def _make_v11_db(db_path: Path) -> None:
    """Build a DB stuck at schema_version 11 with add_week_start_day pending.

    Applies all migrations, then rolls back to version 11 by dropping the
    ``week_start_day`` column and deleting the schema_version rows above 11
    (12 = add_week_start_day, 13 = drop_section_analysis_index), reproducing the
    production state that crashed ``get_athlete_profile``.
    """
    _create_schema_only_db(db_path)
    MigrationRunner(db_path).run_pending()
    conn = duckdb.connect(str(db_path))
    conn.execute("ALTER TABLE athlete_profile DROP COLUMN week_start_day")
    conn.execute("DELETE FROM schema_version WHERE version > 11")
    conn.close()


@pytest.mark.integration
def test_server_startup_applies_migrations(tmp_path: Path) -> None:
    """The worker startup hook applies the pending migration on boot."""
    db_path = tmp_path / "garmin_performance.duckdb"
    _make_v11_db(db_path)
    assert MigrationRunner(db_path).get_current_version() == 11

    applied = worker._apply_startup_migrations(str(db_path))

    assert applied == [
        "add_week_start_day",
        "drop_section_analysis_index",
        "add_section_analysis_run_id",
    ]
    assert MigrationRunner(db_path).get_current_version() == 14


@pytest.mark.integration
def test_read_only_path_after_startup(tmp_path: Path) -> None:
    """A read-only tool reads the new column after the startup hook runs."""
    db_path = tmp_path / "garmin_performance.duckdb"
    _make_v11_db(db_path)

    # Pre-migration row: athlete_profile has no week_start_day column yet.
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "INSERT INTO athlete_profile (user_id, current_focus, focus_notes) "
        "VALUES ('default', 'base', 'notes')"
    )
    conn.close()

    worker._apply_startup_migrations(str(db_path))

    reader = AthleteReader(str(db_path))
    result = reader.get_athlete_profile()

    assert result["current_focus"] == "base"
    assert result["week_start_day"] == 0
