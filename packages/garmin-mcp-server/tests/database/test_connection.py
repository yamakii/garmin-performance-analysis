"""Tests for database connection utilities.

Covers get_db_path(), get_connection(), and get_write_connection().
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.connection import (
    get_connection,
    get_db_path,
    get_write_connection,
)


@pytest.mark.unit
class TestGetDbPath:
    """Tests for get_db_path() resolution."""

    def test_explicit_str_path(self, tmp_path: Path):
        """Explicit string path is returned as Path."""
        db_file = tmp_path / "my.duckdb"
        result = get_db_path(str(db_file))
        assert result == db_file
        assert isinstance(result, Path)

    def test_explicit_path_object(self, tmp_path: Path):
        """Explicit Path object is returned as-is."""
        db_file = tmp_path / "my.duckdb"
        result = get_db_path(db_file)
        assert result == db_file

    def test_none_resolves_via_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """None resolves via GARMIN_DATA_DIR env var."""
        data_dir = tmp_path / "garmin_data"
        data_dir.mkdir()
        monkeypatch.setenv("GARMIN_DATA_DIR", str(data_dir))
        result = get_db_path(None)
        assert result == data_dir / "database" / "garmin_performance.duckdb"

    def test_default_arg_same_as_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Calling get_db_path() with no args is same as None."""
        data_dir = tmp_path / "garmin_data"
        data_dir.mkdir()
        monkeypatch.setenv("GARMIN_DATA_DIR", str(data_dir))
        assert get_db_path() == get_db_path(None)


@pytest.mark.unit
class TestGetConnection:
    """Tests for get_connection() context manager."""

    def test_read_only_connection(self, tmp_path: Path):
        """Connection should be read-only."""
        db_file = tmp_path / "test.duckdb"
        # Create the DB first with write connection
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE t (x INT)")
        conn.close()

        with get_connection(db_file) as conn:
            result = conn.execute("SELECT 1").fetchone()
            assert result == (1,)

    def test_ddl_rejected_on_read_only(self, tmp_path: Path):
        """DDL should be rejected on read-only connection."""
        db_file = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.close()

        with (
            get_connection(db_file) as conn,
            pytest.raises(duckdb.InvalidInputException),
        ):
            conn.execute("CREATE TABLE t (x INT)")

    def test_connection_closed_after_context(self, tmp_path: Path):
        """Connection should be closed after exiting context."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        with get_connection(db_file) as conn:
            ref = conn

        # After context exit, connection is closed — attempting to use it should fail
        with pytest.raises(duckdb.ConnectionException):
            ref.execute("SELECT 1")


@pytest.mark.unit
class TestGetWriteConnection:
    """Tests for get_write_connection() context manager."""

    def test_auto_creates_file(self, tmp_path: Path):
        """Write connection should auto-create DB file."""
        db_file = tmp_path / "new.duckdb"
        assert not db_file.exists()

        with get_write_connection(db_file) as conn:
            conn.execute("CREATE TABLE t (x INT)")

        assert db_file.exists()

    def test_ddl_dml_allowed(self, tmp_path: Path):
        """DDL and DML should work on write connection."""
        db_file = tmp_path / "test.duckdb"

        with get_write_connection(db_file) as conn:
            conn.execute("CREATE TABLE t (x INT)")
            conn.execute("INSERT INTO t VALUES (42)")
            result = conn.execute("SELECT x FROM t").fetchone()
            assert result == (42,)

    def test_connection_closed_after_context(self, tmp_path: Path):
        """Connection should be closed after exiting context."""
        db_file = tmp_path / "test.duckdb"

        with get_write_connection(db_file) as conn:
            ref = conn

        with pytest.raises(duckdb.ConnectionException):
            ref.execute("SELECT 1")
