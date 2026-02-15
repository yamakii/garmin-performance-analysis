"""Tests for Database path configuration."""

import os
from unittest.mock import patch

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter


@pytest.mark.unit
class TestDatabasePaths:
    """Test Database path configuration."""

    def test_db_reader_default_path(self):
        """Test that GarminDBReader uses default database path when no arg provided."""
        from garmin_mcp.utils.paths import get_database_dir

        # Ensure no environment variable is set
        with patch.dict(os.environ, {}, clear=True):
            # Get expected default path
            expected_db_path = get_database_dir() / "garmin_performance.duckdb"

            # Initialize reader without db_path argument
            reader = GarminDBReader()

            # Should use default path from get_database_dir()
            assert reader.db_path == expected_db_path

    def test_db_reader_custom_path_from_env(self, tmp_path):
        """Test that GarminDBReader uses custom database path from environment."""
        custom_data_dir = tmp_path / "custom_data"
        custom_data_dir.mkdir()
        custom_db_dir = custom_data_dir / "database"
        custom_db_dir.mkdir()

        # Set environment variable
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": str(custom_data_dir)}):
            # Initialize reader without db_path argument
            reader = GarminDBReader()

            # Should use custom path from environment
            expected_db_path = custom_db_dir / "garmin_performance.duckdb"
            assert reader.db_path == expected_db_path

    def test_db_reader_explicit_path_overrides_env(self, tmp_path):
        """Test that explicit db_path argument overrides environment variable."""
        custom_data_dir = tmp_path / "custom_data"
        custom_data_dir.mkdir()

        explicit_db_path = tmp_path / "explicit.db"

        # Set environment variable
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": str(custom_data_dir)}):
            # Initialize reader with explicit db_path
            reader = GarminDBReader(db_path=str(explicit_db_path))

            # Should use explicit path, not environment
            assert reader.db_path == explicit_db_path

    def test_db_writer_default_path(self, tmp_path):
        """Test that GarminDBWriter uses default database path when no arg provided."""

        # Ensure no environment variable is set
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("garmin_mcp.utils.paths.get_database_dir", return_value=tmp_path),
        ):
            # Get expected default path
            expected_db_path = tmp_path / "garmin_performance.duckdb"

            # Initialize writer without db_path argument
            writer = GarminDBWriter()

            # Should use default path from get_database_dir()
            assert writer.db_path == expected_db_path

    def test_db_writer_custom_path_from_env(self, tmp_path):
        """Test that GarminDBWriter uses custom database path from environment."""
        custom_data_dir = tmp_path / "custom_data"
        custom_data_dir.mkdir()
        custom_db_dir = custom_data_dir / "database"
        custom_db_dir.mkdir()

        # Set environment variable
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": str(custom_data_dir)}):
            # Initialize writer without db_path argument
            writer = GarminDBWriter()

            # Should use custom path from environment
            expected_db_path = custom_db_dir / "garmin_performance.duckdb"
            assert writer.db_path == expected_db_path
