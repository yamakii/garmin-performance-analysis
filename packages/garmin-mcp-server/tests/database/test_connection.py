"""Tests for database connection utilities.

Covers get_db_path(), get_connection(), get_write_connection(),
and _connect_with_retry().
"""

from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from garmin_mcp.database.connection import (
    _connect_with_retry,
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


@pytest.mark.unit
class TestConnectWithRetry:
    """Tests for _connect_with_retry() lock handling."""

    def test_retry_succeeds_on_second_attempt(self, tmp_path: Path):
        """Should succeed when lock clears on retry."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        lock_error = duckdb.IOException("Could not set lock on file")
        mock_conn = duckdb.connect(str(db_file), read_only=True)

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = [lock_error, mock_conn]
            conn = _connect_with_retry(db_file, read_only=True, retries=3, backoff=0.01)
            assert conn is mock_conn
            assert mock_connect.call_count == 2
        mock_conn.close()

    def test_raises_after_max_retries(self, tmp_path: Path):
        """Should raise after exhausting all retries."""
        db_file = tmp_path / "test.duckdb"
        lock_error = duckdb.IOException("Could not set lock on file")

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = lock_error
            with pytest.raises(duckdb.IOException, match="Could not set lock"):
                _connect_with_retry(db_file, read_only=True, retries=2, backoff=0.01)
            # Initial attempt + 2 retries = 3 calls
            assert mock_connect.call_count == 3

    def test_non_lock_ioexception_raises_immediately(self, tmp_path: Path):
        """Non-lock IOException should not be retried."""
        db_file = tmp_path / "test.duckdb"
        other_error = duckdb.IOException("Permission denied")

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = other_error
            with pytest.raises(duckdb.IOException, match="Permission denied"):
                _connect_with_retry(db_file, read_only=True, retries=3, backoff=0.01)
            assert mock_connect.call_count == 1

    def test_read_connection_retries_on_lock(self, tmp_path: Path):
        """get_connection() should retry on lock errors."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        lock_error = duckdb.IOException("Could not set lock on file")
        real_conn = duckdb.connect(str(db_file), read_only=True)

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = [lock_error, real_conn]
            with get_connection(db_file, retries=3, backoff=0.01) as conn:
                result = conn.execute("SELECT 1").fetchone()
                assert result == (1,)

    def test_write_connection_retries_on_lock(self, tmp_path: Path):
        """get_write_connection() should retry on lock errors."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        lock_error = duckdb.IOException("Could not set lock on file")
        real_conn = duckdb.connect(str(db_file))

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = [lock_error, real_conn]
            with get_write_connection(db_file, retries=3, backoff=0.01) as conn:
                result = conn.execute("SELECT 1").fetchone()
                assert result == (1,)

    def test_zero_retries_no_retry(self, tmp_path: Path):
        """With retries=0, lock error should raise immediately."""
        db_file = tmp_path / "test.duckdb"
        lock_error = duckdb.IOException("Could not set lock on file")

        with patch("garmin_mcp.database.connection.duckdb.connect") as mock_connect:
            mock_connect.side_effect = lock_error
            with pytest.raises(duckdb.IOException, match="Could not set lock"):
                _connect_with_retry(db_file, read_only=True, retries=0, backoff=0.01)
            assert mock_connect.call_count == 1
