"""Tests for MigrationRunner schema version tracking."""

import shutil
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.migrations.runner import MigrationRunner


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

        assert len(applied) == 5
        assert applied[0] == "phase0_power_prep"
        assert applied[-1] == "add_plan_versioning"
        assert runner.get_current_version() == 5

    def test_run_pending_skips_applied(self, db_path: Path) -> None:
        """Running twice applies nothing the second time."""
        runner = MigrationRunner(db_path)
        first = runner.run_pending()
        second = runner.run_pending()

        assert len(first) == 5
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

        assert runner.get_current_version() == 5
        assert applied == ["remove_fk_constraints", "add_plan_versioning"]

    def test_migration_records_applied_at(self, db_path: Path) -> None:
        """Each applied migration records a timestamp."""
        runner = MigrationRunner(db_path)
        runner.run_pending()

        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_version ORDER BY version"
        ).fetchall()
        conn.close()

        assert len(rows) == 5
        for version, name, applied_at in rows:
            assert applied_at is not None
            assert isinstance(name, str)
            assert version > 0
