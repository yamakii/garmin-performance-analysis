"""Tests for BaseDBReader.

Covers init path resolution, DB-not-found warning, and read-only guarantee.
"""

import logging
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.base import BaseDBReader


@pytest.mark.unit
class TestBaseDBReaderInit:
    """Tests for BaseDBReader.__init__() path resolution."""

    def test_explicit_path_stored(self, tmp_path: Path):
        """Explicit path is stored as Path object."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()
        reader = BaseDBReader(db_path=str(db_file))
        assert reader.db_path == db_file

    def test_none_resolves_via_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """None resolves via GARMIN_DATA_DIR env var."""
        data_dir = tmp_path / "garmin_data"
        data_dir.mkdir()
        monkeypatch.setenv("GARMIN_DATA_DIR", str(data_dir))
        reader = BaseDBReader(db_path=None)
        assert reader.db_path == data_dir / "database" / "garmin_performance.duckdb"

    def test_warning_when_db_not_exists(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """Warning logged when DB file doesn't exist."""
        db_file = tmp_path / "nonexistent.duckdb"
        with caplog.at_level(
            logging.WARNING, logger="garmin_mcp.database.readers.base"
        ):
            BaseDBReader(db_path=str(db_file))
        assert "Database not found" in caplog.text

    def test_no_warning_when_db_exists(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """No warning logged when DB file exists."""
        db_file = tmp_path / "exists.duckdb"
        duckdb.connect(str(db_file)).close()
        with caplog.at_level(
            logging.WARNING, logger="garmin_mcp.database.readers.base"
        ):
            BaseDBReader(db_path=str(db_file))
        assert "Database not found" not in caplog.text


@pytest.mark.unit
class TestBaseDBReaderConnection:
    """Tests for BaseDBReader._get_connection()."""

    def test_get_connection_read_only(self, tmp_path: Path):
        """_get_connection() returns a read-only connection."""
        db_file = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_file))
        conn.execute("CREATE TABLE t (x INT)")
        conn.close()

        reader = BaseDBReader(db_path=str(db_file))
        with reader._get_connection() as conn:
            result = conn.execute("SELECT 1").fetchone()
            assert result == (1,)

    def test_get_connection_ddl_rejected(self, tmp_path: Path):
        """DDL should be rejected on reader connection."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        reader = BaseDBReader(db_path=str(db_file))
        with (
            reader._get_connection() as conn,
            pytest.raises(duckdb.InvalidInputException),
        ):
            conn.execute("CREATE TABLE t (x INT)")

    def test_get_connection_closes_after_context(self, tmp_path: Path):
        """Connection is closed after context manager exits."""
        db_file = tmp_path / "test.duckdb"
        duckdb.connect(str(db_file)).close()

        reader = BaseDBReader(db_path=str(db_file))
        with reader._get_connection() as conn:
            ref = conn

        with pytest.raises(duckdb.ConnectionException):
            ref.execute("SELECT 1")
