"""Unit tests for path configuration utilities.

Tests the configurable data paths feature that allows users to
customize data and result directory locations via environment variables.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.utils.paths import (
    get_data_base_dir,
    get_database_dir,
    get_performance_dir,
    get_precheck_dir,
    get_raw_dir,
    get_result_dir,
    get_weight_raw_dir,
)


@pytest.mark.unit
class TestGetDataBaseDir:
    """Tests for get_data_base_dir() function."""

    def test_get_data_base_dir_default(self) -> None:
        """Test that default path is project_root/data when env var is not set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove GARMIN_DATA_DIR if it exists
            if "GARMIN_DATA_DIR" in os.environ:
                del os.environ["GARMIN_DATA_DIR"]

            data_dir = get_data_base_dir()

            # Should return project_root/data
            assert data_dir.name == "data"
            assert data_dir.is_absolute()
            # Verify it's under the project root (monorepo)
            assert (data_dir.parent / "packages").exists()
            assert (data_dir.parent / ".git").exists()

    def test_get_data_base_dir_custom(self) -> None:
        """Test that custom path is used when GARMIN_DATA_DIR env var is set."""
        custom_path = "/tmp/custom_garmin_data"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_path}):
            data_dir = get_data_base_dir()

            assert data_dir == Path(custom_path).resolve()
            assert data_dir.is_absolute()

    def test_get_data_base_dir_absolute(self) -> None:
        """Test that absolute path is correctly resolved."""
        custom_path = "/home/user/garmin_data"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_path}):
            data_dir = get_data_base_dir()

            assert data_dir == Path(custom_path)
            assert data_dir.is_absolute()

    def test_get_data_base_dir_relative_to_absolute(self) -> None:
        """Test that relative path is converted to absolute."""
        custom_path = "./my_data"
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": custom_path}):
            data_dir = get_data_base_dir()

            assert data_dir.is_absolute()
            assert data_dir.name == "my_data"


@pytest.mark.unit
class TestGetResultDir:
    """Tests for get_result_dir() function."""

    def test_get_result_dir_default(self) -> None:
        """Test that default path is project_root/result when env var is not set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove GARMIN_RESULT_DIR if it exists
            if "GARMIN_RESULT_DIR" in os.environ:
                del os.environ["GARMIN_RESULT_DIR"]

            result_dir = get_result_dir()

            # Should return project_root/result
            assert result_dir.name == "result"
            assert result_dir.is_absolute()
            # Verify it's under the project root (monorepo)
            assert (result_dir.parent / "packages").exists()
            assert (result_dir.parent / ".git").exists()

    def test_get_result_dir_custom(self) -> None:
        """Test that custom path is used when GARMIN_RESULT_DIR env var is set."""
        custom_path = "/tmp/custom_garmin_results"
        with patch.dict(os.environ, {"GARMIN_RESULT_DIR": custom_path}):
            result_dir = get_result_dir()

            assert result_dir == Path(custom_path).resolve()
            assert result_dir.is_absolute()


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for helper functions that return subdirectories."""

    def test_get_raw_dir(self) -> None:
        """Test that get_raw_dir() returns data_base_dir/raw."""
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": "/tmp/test_data"}):
            raw_dir = get_raw_dir()

            expected = Path("/tmp/test_data/raw")
            assert raw_dir == expected

    def test_get_performance_dir(self) -> None:
        """Test that get_performance_dir() returns data_base_dir/performance."""
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": "/tmp/test_data"}):
            performance_dir = get_performance_dir()

            expected = Path("/tmp/test_data/performance")
            assert performance_dir == expected

    def test_get_precheck_dir(self) -> None:
        """Test that get_precheck_dir() returns data_base_dir/precheck."""
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": "/tmp/test_data"}):
            precheck_dir = get_precheck_dir()

            expected = Path("/tmp/test_data/precheck")
            assert precheck_dir == expected

    def test_get_database_dir(self) -> None:
        """Test that get_database_dir() returns data_base_dir/database."""
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": "/tmp/test_data"}):
            database_dir = get_database_dir()

            expected = Path("/tmp/test_data/database")
            assert database_dir == expected

    def test_get_weight_raw_dir(self) -> None:
        """Test that get_weight_raw_dir() returns data_base_dir/raw/weight."""
        with patch.dict(os.environ, {"GARMIN_DATA_DIR": "/tmp/test_data"}):
            weight_raw_dir = get_weight_raw_dir()

            expected = Path("/tmp/test_data/raw/weight")
            assert weight_raw_dir == expected

    def test_helper_functions_use_default_base(self) -> None:
        """Test that helper functions use default base dir when no env var is set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove GARMIN_DATA_DIR if it exists
            if "GARMIN_DATA_DIR" in os.environ:
                del os.environ["GARMIN_DATA_DIR"]

            raw_dir = get_raw_dir()
            performance_dir = get_performance_dir()
            precheck_dir = get_precheck_dir()
            database_dir = get_database_dir()
            weight_raw_dir = get_weight_raw_dir()

            # All should be under project_root/data
            assert raw_dir.parent.name == "data"
            assert performance_dir.parent.name == "data"
            assert precheck_dir.parent.name == "data"
            assert database_dir.parent.name == "data"
            assert weight_raw_dir.parent.parent.name == "data"

            # Check subdirectory names
            assert raw_dir.name == "raw"
            assert performance_dir.name == "performance"
            assert precheck_dir.name == "precheck"
            assert database_dir.name == "database"
            assert weight_raw_dir.name == "weight"
