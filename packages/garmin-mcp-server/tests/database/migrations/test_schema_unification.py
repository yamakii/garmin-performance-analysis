"""Tests for schema DDL unification (issue #342).

Verifies that the base schema (``GarminDBWriter._ensure_tables``) and the
migrations together build the full schema on a fresh DB, that re-initialising an
existing DB is idempotent, and that no table is created by both the base schema
and a migration (single source of truth).
"""

import inspect
import re
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.migrations import add_athlete_tables as athlete_module
from garmin_mcp.database.migrations.runner import MigrationRunner

# Tables created by the base schema (_ensure_tables).
BASE_TABLES = {
    "activities",
    "splits",
    "form_efficiency",
    "heart_rate_zones",
    "hr_efficiency",
    "performance_trends",
    "vo2_max",
    "lactate_threshold",
    "body_composition",
    "form_baseline_history",
    "form_evaluations",
    "section_analyses",
    "time_series_metrics",
}

# Tables owned exclusively by migrations/add_athlete_tables.py (version 7).
ATHLETE_TABLES = {
    "athlete_profile",
    "athlete_goals",
    "season_retrospectives",
    "weekly_reviews",
}

ALL_TABLES = BASE_TABLES | ATHLETE_TABLES

REQUIRED_SEQUENCES = {
    "form_evaluations_seq",
    "form_baseline_history_seq",
    "seq_section_analyses_id",
    "seq_analysis_run_id",
    "seq_athlete_goals_id",
    "seq_season_retrospectives_id",
    "seq_weekly_reviews_id",
}

REQUIRED_INDEXES = {
    "idx_time_series_activity",
    "idx_time_series_timestamp",
    # idx_activity_section removed in #720: section_analyses is append-only, so
    # the unique index on (activity_id, section_type) is no longer created.
}


def _table_names(db_path: Path) -> set[str]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _sequence_names(db_path: Path) -> set[str]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute("SELECT sequence_name FROM duckdb_sequences()").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _index_names(db_path: Path) -> set[str]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _created_tables_in_source(source: str) -> set[str]:
    """Extract table names from ``CREATE TABLE [IF NOT EXISTS] <name>`` in source."""
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    return {m.group(1) for m in pattern.finditer(source)}


@pytest.mark.integration
def test_fresh_db_has_all_tables(tmp_path: Path) -> None:
    """A brand-new DB gets every table (incl. the 4 athlete tables), the
    required sequences and indexes after GarminDBWriter() runs base schema +
    migrations."""
    db_path = tmp_path / "fresh.duckdb"

    GarminDBWriter(db_path=str(db_path))

    tables = _table_names(db_path)
    missing = ALL_TABLES - tables
    assert not missing, f"Fresh DB is missing tables: {sorted(missing)}"

    sequences = _sequence_names(db_path)
    missing_seq = REQUIRED_SEQUENCES - sequences
    assert not missing_seq, f"Fresh DB is missing sequences: {sorted(missing_seq)}"

    indexes = _index_names(db_path)
    missing_idx = REQUIRED_INDEXES - indexes
    assert not missing_idx, f"Fresh DB is missing indexes: {sorted(missing_idx)}"


@pytest.mark.integration
def test_fresh_db_schema_version_recorded(tmp_path: Path) -> None:
    """After building a fresh DB, schema_version records the latest migration."""
    db_path = tmp_path / "fresh_version.duckdb"

    GarminDBWriter(db_path=str(db_path))

    runner = MigrationRunner(db_path)
    latest_version = runner.get_current_version()

    # Latest version equals the highest registered migration version.
    from garmin_mcp.database.migrations.registry import MIGRATIONS

    expected_latest = max(version for version, _, _ in MIGRATIONS)
    assert latest_version == expected_latest


@pytest.mark.integration
def test_reinit_is_idempotent(tmp_path: Path) -> None:
    """Re-instantiating GarminDBWriter on an existing DB does not error and does
    not change the table set."""
    db_path = tmp_path / "reinit.duckdb"

    GarminDBWriter(db_path=str(db_path))
    tables_after_first = _table_names(db_path)

    # Second instantiation must be a no-op (no exception, same tables).
    GarminDBWriter(db_path=str(db_path))
    tables_after_second = _table_names(db_path)

    assert tables_after_first == tables_after_second
    assert tables_after_second >= ALL_TABLES


@pytest.mark.unit
def test_no_duplicate_ddl_between_ensure_and_migration() -> None:
    """The base schema (_ensure_tables) and the athlete migration must not both
    create the same table (single source of truth, issue #342)."""
    ensure_source = inspect.getsource(GarminDBWriter._ensure_tables)
    athlete_source = inspect.getsource(athlete_module.add_athlete_tables)

    ensure_tables = _created_tables_in_source(ensure_source)
    athlete_tables = _created_tables_in_source(athlete_source)

    overlap = ensure_tables & athlete_tables
    assert not overlap, (
        "Duplicate CREATE TABLE DDL between _ensure_tables and "
        f"add_athlete_tables: {sorted(overlap)}"
    )

    # Sanity: the athlete migration still owns all four athlete tables, and the
    # base schema does not create any of them.
    assert athlete_tables >= ATHLETE_TABLES
    assert not (ATHLETE_TABLES & ensure_tables)
