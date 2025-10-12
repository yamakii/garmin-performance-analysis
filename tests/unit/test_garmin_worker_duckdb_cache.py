"""
Unit tests for GarminIngestWorker DuckDB cache checking.

Tests the _check_duckdb_cache() method that checks if activity data
exists in DuckDB and returns complete performance data if available.
"""

from unittest.mock import Mock

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance for testing."""
    return GarminIngestWorker()


@pytest.fixture
def mock_db_reader():
    """Create mock GarminDBReader."""
    return Mock()


class TestCheckDuckDBCache:
    """Tests for _check_duckdb_cache() method."""

    @pytest.mark.unit
    def test_check_duckdb_cache_complete(self, worker, mock_db_reader):
        """Test DuckDB cache check returns None (not implemented for normalized schema)."""
        # Arrange
        activity_id = 12345678
        worker._db_reader = mock_db_reader

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        # DuckDB cache checking is not implemented for normalized schema
        # Should always return None to trigger reprocessing
        assert result is None

    @pytest.mark.unit
    def test_check_duckdb_cache_partial(self, worker, mock_db_reader):
        """Test DuckDB cache check returns None (not implemented)."""
        # Arrange
        activity_id = 12345678
        worker._db_reader = mock_db_reader

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        assert result is None  # Should always return None (not implemented)

    @pytest.mark.unit
    def test_check_duckdb_cache_missing(self, worker, mock_db_reader):
        """Test DuckDB cache check returns None (not implemented)."""
        # Arrange
        activity_id = 12345678
        worker._db_reader = mock_db_reader

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        assert result is None

    @pytest.mark.unit
    def test_check_duckdb_cache_db_reader_none(self, worker):
        """Test DuckDB cache check when db_reader is None."""
        # Arrange
        activity_id = 12345678
        worker._db_reader = None

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        assert result is None
