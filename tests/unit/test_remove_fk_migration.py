"""Unit tests for FK constraint removal migration script.

Test coverage:
- Backup table creation
- Drop old tables
- Create new tables without FK
- Restore data from backup
- Verify data integrity
- Cleanup backup tables
- Transaction rollback on error
"""

import duckdb
import pytest

# Import will fail initially (TDD Red phase)
# from tools.database.migrations.remove_fk_constraints import (
#     migrate_remove_fk_constraints,
#     _backup_tables,
#     _drop_old_tables,
#     _create_new_tables,
#     _restore_data,
#     _verify_data_integrity,
#     _cleanup_backup_tables,
# )


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test_migration.duckdb"
    return db_path


@pytest.fixture
def populated_db(test_db_path):
    """Create test database with sample data in splits table."""
    conn = duckdb.connect(str(test_db_path))

    # Create activities table (parent)
    conn.execute(
        """
        CREATE TABLE activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE NOT NULL,
            activity_name VARCHAR
        )
    """
    )

    # Create splits table with FK constraint
    conn.execute(
        """
        CREATE TABLE splits (
            activity_id BIGINT,
            split_index INTEGER,
            distance DOUBLE,
            pace_seconds_per_km DOUBLE,
            PRIMARY KEY (activity_id, split_index),
            FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
        )
    """
    )

    # Insert sample data
    conn.execute("INSERT INTO activities VALUES (12345, '2025-10-15', 'Morning Run')")
    conn.execute("INSERT INTO activities VALUES (67890, '2025-10-16', 'Evening Run')")

    conn.execute("INSERT INTO splits VALUES (12345, 1, 1.0, 300.0)")
    conn.execute("INSERT INTO splits VALUES (12345, 2, 1.0, 295.0)")
    conn.execute("INSERT INTO splits VALUES (67890, 1, 1.0, 310.0)")

    conn.close()
    return test_db_path


class TestBackupTables:
    """Test backup table creation."""

    def test_backup_tables_creates_backup(self, populated_db):
        """Test that backup tables are created with _backup_fk suffix."""
        # Import the function (will fail - TDD RED)
        from tools.database.migrations.remove_fk_constraints import _backup_tables

        conn = duckdb.connect(str(populated_db))

        # Execute backup
        _backup_tables(conn, ["splits"])

        # Verify backup table exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits_backup_fk'"
        ).fetchone()
        assert result is not None

        # Verify data copied
        count_original = conn.execute("SELECT COUNT(*) FROM splits").fetchone()[0]
        count_backup = conn.execute("SELECT COUNT(*) FROM splits_backup_fk").fetchone()[
            0
        ]
        assert count_original == count_backup
        assert count_backup == 3

        conn.close()


class TestDropOldTables:
    """Test dropping old tables with FK constraints."""

    def test_drop_old_tables_removes_tables(self, populated_db):
        """Test that old tables are dropped successfully."""
        from tools.database.migrations.remove_fk_constraints import (
            _backup_tables,
            _drop_old_tables,
        )

        conn = duckdb.connect(str(populated_db))

        # Backup first (prerequisite)
        _backup_tables(conn, ["splits"])

        # Drop old table
        _drop_old_tables(conn, ["splits"])

        # Verify table no longer exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits'"
        ).fetchall()
        assert len(result) == 0

        # Verify backup still exists
        result_backup = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits_backup_fk'"
        ).fetchone()
        assert result_backup is not None

        conn.close()


class TestCreateNewTables:
    """Test creating new tables without FK constraints."""

    def test_create_new_tables_without_fk(self, test_db_path):
        """Test that new tables are created without FK constraints."""
        from tools.database.migrations.remove_fk_constraints import _create_new_tables

        conn = duckdb.connect(str(test_db_path))

        # Create activities table (parent - needed for FK check)
        conn.execute(
            """
            CREATE TABLE activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL,
                activity_name VARCHAR
            )
        """
        )

        # Create new splits table without FK
        _create_new_tables(conn, ["splits"])

        # Verify table exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits'"
        ).fetchone()
        assert result is not None

        # Verify NO foreign key constraints by inserting orphaned record
        # If FK exists, this would fail; if no FK, it succeeds
        conn.execute(
            """
            INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km)
            VALUES (99999, 1, 1.0, 300.0)
        """
        )
        count = conn.execute("SELECT COUNT(*) FROM splits").fetchone()[0]
        assert count == 1  # Orphaned record inserted successfully (no FK constraint)

        conn.close()


class TestRestoreData:
    """Test data restoration from backup tables."""

    def test_restore_data_preserves_records(self, populated_db):
        """Test that data is completely restored from backup."""
        from tools.database.migrations.remove_fk_constraints import (
            _backup_tables,
            _create_new_tables,
            _drop_old_tables,
            _restore_data,
        )

        conn = duckdb.connect(str(populated_db))

        # Execute migration steps
        _backup_tables(conn, ["splits"])
        _drop_old_tables(conn, ["splits"])
        _create_new_tables(conn, ["splits"])
        _restore_data(conn, ["splits"])

        # Verify data restored (populated_db has 3 rows)
        count = conn.execute("SELECT COUNT(*) FROM splits").fetchone()[0]
        assert count == 3

        # Verify data content (check only the columns from populated_db fixture)
        result = conn.execute(
            "SELECT activity_id, split_index, distance, pace_seconds_per_km FROM splits ORDER BY activity_id, split_index"
        ).fetchall()
        assert len(result) == 3
        assert result[0][0] == 12345  # activity_id
        assert result[0][1] == 1  # split_index
        assert result[0][2] == 1.0  # distance
        assert result[0][3] == 300.0  # pace

        conn.close()


class TestVerifyDataIntegrity:
    """Test data integrity verification."""

    def test_verify_data_integrity_detects_mismatch(self, test_db_path):
        """Test that data integrity verification detects mismatches."""
        from tools.database.migrations.remove_fk_constraints import (
            _verify_data_integrity,
        )

        conn = duckdb.connect(str(test_db_path))

        # Setup: Create tables with mismatched counts
        conn.execute(
            """
            CREATE TABLE splits (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                pace_seconds_per_km DOUBLE,
                PRIMARY KEY (activity_id, split_index)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE splits_backup_fk (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                pace_seconds_per_km DOUBLE
            )
        """
        )

        # Insert different counts
        conn.execute("INSERT INTO splits VALUES (12345, 1, 1.0, 300.0)")
        conn.execute("INSERT INTO splits VALUES (12345, 2, 1.0, 295.0)")

        conn.execute("INSERT INTO splits_backup_fk VALUES (12345, 1, 1.0, 300.0)")
        conn.execute("INSERT INTO splits_backup_fk VALUES (12345, 2, 1.0, 295.0)")
        conn.execute(
            "INSERT INTO splits_backup_fk VALUES (12345, 3, 1.0, 290.0)"
        )  # Extra row

        # Verify should detect mismatch
        with pytest.raises(AssertionError, match="Data integrity check failed"):
            _verify_data_integrity(conn, ["splits"])

        conn.close()


class TestCleanupBackupTables:
    """Test cleanup of backup tables."""

    def test_cleanup_removes_backup_tables(self, test_db_path):
        """Test that backup tables are removed after successful migration."""
        from tools.database.migrations.remove_fk_constraints import (
            _backup_tables,
            _cleanup_backup_tables,
        )

        conn = duckdb.connect(str(test_db_path))

        # Setup: Create table and backup
        conn.execute(
            """
            CREATE TABLE splits (
                activity_id BIGINT,
                split_index INTEGER,
                PRIMARY KEY (activity_id, split_index)
            )
        """
        )
        conn.execute("INSERT INTO splits VALUES (12345, 1)")

        _backup_tables(conn, ["splits"])

        # Verify backup exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits_backup_fk'"
        ).fetchone()
        assert result is not None

        # Cleanup
        _cleanup_backup_tables(conn, ["splits"])

        # Verify backup removed
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits_backup_fk'"
        ).fetchall()
        assert len(result) == 0

        # Verify original table still exists
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'splits'"
        ).fetchone()
        assert result is not None

        conn.close()


class TestMigrationRollback:
    """Test transaction rollback on error."""

    def test_migration_rollback_on_error(self, test_db_path):
        """Test that migration rolls back on error."""
        from tools.database.migrations.remove_fk_constraints import (
            migrate_remove_fk_constraints,
        )

        conn = duckdb.connect(str(test_db_path))

        # Setup: Create minimal schema (only activities, no splits)
        conn.execute(
            """
            CREATE TABLE activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL,
                activity_name VARCHAR
            )
        """
        )
        conn.execute("INSERT INTO activities VALUES (12345, '2025-10-15', 'Run')")

        # Note: splits table doesn't exist, so migration should fail
        conn.close()

        # Execute migration (should fail and rollback)
        with pytest.raises(Exception, match="Migration failed"):
            migrate_remove_fk_constraints(str(test_db_path), dry_run=False)

        # Verify database is unchanged (rollback succeeded)
        conn = duckdb.connect(str(test_db_path))

        # activities table should still exist
        activities_count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        assert activities_count == 1

        # No backup tables should exist
        backup_tables = conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name LIKE '%_backup_fk'
        """
        ).fetchall()
        assert len(backup_tables) == 0

        conn.close()
