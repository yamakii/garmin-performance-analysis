"""Tests for MigrationRunner schema version tracking."""

import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.runner import (
    MigrationRunner,
    ensure_schema_current,
)


def _make_v11_db(db_path: Path) -> None:
    """Build a DB stuck at schema_version 11 with add_week_start_day pending.

    Applies all migrations, then rolls back to version 11 by dropping the
    ``week_start_day`` column and deleting the schema_version rows for every
    migration above 11 (12 = add_week_start_day onward), simulating the real
    production state that crashed ``get_athlete_profile`` (issue #631).
    """
    _create_schema_only_db(db_path)
    MigrationRunner(db_path).run_pending()
    conn = duckdb.connect(str(db_path))
    conn.execute("ALTER TABLE athlete_profile DROP COLUMN week_start_day")
    conn.execute("DELETE FROM schema_version WHERE version > 11")
    conn.close()


def _create_schema_only_db(db_path: Path) -> None:
    """Create a DB with full schema but no schema_version table.

    Simulates a pre-migration database by calling _ensure_tables() directly
    without running migrations.
    """
    from garmin_mcp.database.db_writer import GarminDBWriter

    writer = object.__new__(GarminDBWriter)
    writer.db_path = db_path
    writer._ensure_tables()


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped template: tables only, no migrations applied."""
    tmp_path = tmp_path_factory.mktemp("migration_template")
    db_path = tmp_path / "template.duckdb"
    _create_schema_only_db(db_path)
    return db_path


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template), str(dest))
    return dest


@pytest.mark.unit
class TestMigrationRunner:
    """Tests for MigrationRunner."""

    def test_schema_version_table_created(self, tmp_path: Path) -> None:
        """Empty DB gets schema_version table on first access."""
        db_path = tmp_path / "empty.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities "
            "(activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.close()

        runner = MigrationRunner(db_path)
        version = runner.get_current_version()

        assert version == 0

        conn = duckdb.connect(str(db_path), read_only=True)
        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        conn.close()
        assert "schema_version" in tables

    def test_get_current_version_empty(self, db_path: Path) -> None:
        """Empty schema_version table returns version 0."""
        runner = MigrationRunner(db_path)
        assert runner.get_current_version() == 0

    def test_run_pending_applies_all(self, db_path: Path) -> None:
        """All migrations are applied on a fresh DB."""
        runner = MigrationRunner(db_path)
        applied = runner.run_pending()

        assert len(applied) == 19
        assert applied[0] == "phase0_power_prep"
        assert applied[-1] == "add_pace_consistency_full"
        assert runner.get_current_version() == 19

    def test_run_pending_skips_applied(self, db_path: Path) -> None:
        """Running twice applies nothing the second time."""
        runner = MigrationRunner(db_path)
        first = runner.run_pending()
        second = runner.run_pending()

        assert len(first) == 19
        assert second == []

    def test_run_pending_partial(self, db_path: Path) -> None:
        """Only migrations above current version are applied."""
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT current_timestamp
            )
        """)
        for v, name in [
            (1, "phase0_power_prep"),
            (2, "phase1_power_efficiency"),
            (3, "phase2_integrated_score"),
        ]:
            conn.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                [v, name],
            )
        conn.close()

        runner = MigrationRunner(db_path)
        applied = runner.run_pending()

        assert runner.get_current_version() == 19
        assert applied == [
            "remove_fk_constraints",
            "add_plan_versioning",
            "add_cadence_columns",
            "add_athlete_tables",
            "drop_weekly_review_index",
            "add_body_composition_date_index",
            "add_strength_sessions",
            "add_daily_wellness_table",
            "add_week_start_day",
            "drop_section_analysis_index",
            "add_sync_runs_table",
            "add_section_analysis_run_id",
            "add_trend_analyses_table",
            "drop_plan_tables",
            "add_analysis_runs_table",
            "add_pace_consistency_full",
        ]

    def test_migration_records_applied_at(self, db_path: Path) -> None:
        """Each applied migration records a timestamp."""
        runner = MigrationRunner(db_path)
        runner.run_pending()

        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_version ORDER BY version"
        ).fetchall()
        conn.close()

        assert len(rows) == 19
        for version, name, applied_at in rows:
            assert applied_at is not None
            assert isinstance(name, str)
            assert version > 0


@pytest.mark.unit
class TestEnsureSchemaCurrent:
    """Tests for the ensure_schema_current startup helper."""

    def test_ensure_schema_current_applies_pending(self, tmp_path: Path) -> None:
        """A DB at version 11 is migrated to 19 and gains week_start_day."""
        db_path = tmp_path / "v11.duckdb"
        _make_v11_db(db_path)
        runner = MigrationRunner(db_path)
        assert runner.get_current_version() == 11

        applied = ensure_schema_current(db_path)

        assert applied == [
            "add_week_start_day",
            "drop_section_analysis_index",
            "add_sync_runs_table",
            "add_section_analysis_run_id",
            "add_trend_analyses_table",
            "drop_plan_tables",
            "add_analysis_runs_table",
            "add_pace_consistency_full",
        ]
        assert runner.get_current_version() == 19

        conn = duckdb.connect(str(db_path), read_only=True)
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(athlete_profile)").fetchall()
        ]
        conn.close()
        assert "week_start_day" in columns

    def test_ensure_schema_current_noop_when_uptodate(self, db_path: Path) -> None:
        """An up-to-date DB yields no applied migrations and re-runs cleanly."""
        MigrationRunner(db_path).run_pending()
        assert MigrationRunner(db_path).get_current_version() == 19

        first = ensure_schema_current(db_path)
        second = ensure_schema_current(db_path)

        assert first == []
        assert second == []
        assert MigrationRunner(db_path).get_current_version() == 19
