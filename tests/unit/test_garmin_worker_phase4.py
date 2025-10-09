"""
Unit tests for GarminIngestWorker Phase 4: process_activity_by_date integration.

Tests the new resolver methods and process_activity_by_date delegation:
- _resolve_activity_id_from_duckdb(date: str) -> int | None
- _resolve_activity_id_from_api(date: str) -> int
- process_activity_by_date(date: str) delegation to process_activity()
"""

from unittest.mock import Mock, patch

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


@pytest.fixture
def mock_garmin_client():
    """Create mock Garmin client."""
    return Mock()


class TestResolveActivityIdFromDuckDB:
    """Tests for _resolve_activity_id_from_duckdb() method."""

    @pytest.mark.unit
    def test_resolve_activity_id_from_duckdb_found(self, worker, mock_db_reader):
        """Test DuckDB resolution when activity is found."""
        # Arrange
        date = "2025-10-05"
        expected_activity_id = 20594901208

        # Mock db_reader to return activity_id
        mock_db_reader.query_activity_by_date.return_value = expected_activity_id
        worker._db_reader = mock_db_reader

        # Act
        result = worker._resolve_activity_id_from_duckdb(date)

        # Assert
        assert result == expected_activity_id
        mock_db_reader.query_activity_by_date.assert_called_once_with(date)

    @pytest.mark.unit
    def test_resolve_activity_id_from_duckdb_not_found(self, worker, mock_db_reader):
        """Test DuckDB resolution when activity is not found."""
        # Arrange
        date = "2025-10-05"

        # Mock db_reader to return None
        mock_db_reader.query_activity_by_date.return_value = None
        worker._db_reader = mock_db_reader

        # Act
        result = worker._resolve_activity_id_from_duckdb(date)

        # Assert
        assert result is None
        mock_db_reader.query_activity_by_date.assert_called_once_with(date)

    @pytest.mark.unit
    def test_resolve_activity_id_from_duckdb_no_reader(self, worker):
        """Test DuckDB resolution when db_reader is None."""
        # Arrange
        date = "2025-10-05"
        worker._db_reader = None

        # Act
        result = worker._resolve_activity_id_from_duckdb(date)

        # Assert
        assert result is None


class TestResolveActivityIdFromAPI:
    """Tests for _resolve_activity_id_from_api() method."""

    @pytest.mark.unit
    def test_resolve_activity_id_from_api_single(self, worker, mock_garmin_client):
        """Test API resolution when single activity is found."""
        # Arrange
        date = "2025-10-05"
        expected_activity_id = 20594901208

        # Mock API response with single activity
        mock_garmin_client.get_activities_fordate.return_value = {
            "ActivitiesForDay": {
                "payload": [
                    {"activityId": expected_activity_id, "activityName": "Morning Run"}
                ]
            }
        }

        with patch.object(worker, "get_garmin_client", return_value=mock_garmin_client):
            # Act
            result = worker._resolve_activity_id_from_api(date)

            # Assert
            assert result == expected_activity_id
            mock_garmin_client.get_activities_fordate.assert_called_once_with(date)

    @pytest.mark.unit
    def test_resolve_activity_id_from_api_multiple(self, worker, mock_garmin_client):
        """Test API resolution when multiple activities are found (should raise error)."""
        # Arrange
        date = "2025-10-05"

        # Mock API response with multiple activities
        mock_garmin_client.get_activities_fordate.return_value = {
            "ActivitiesForDay": {
                "payload": [
                    {"activityId": 123456, "activityName": "Morning Run"},
                    {"activityId": 789012, "activityName": "Evening Run"},
                ]
            }
        }

        with (
            patch.object(worker, "get_garmin_client", return_value=mock_garmin_client),
            pytest.raises(ValueError, match="Multiple activities found"),
        ):
            worker._resolve_activity_id_from_api(date)

    @pytest.mark.unit
    def test_resolve_activity_id_from_api_none(self, worker, mock_garmin_client):
        """Test API resolution when no activities are found (should raise error)."""
        # Arrange
        date = "2025-10-05"

        # Mock API response with no activities
        mock_garmin_client.get_activities_fordate.return_value = {
            "ActivitiesForDay": {"payload": []}
        }

        with (
            patch.object(worker, "get_garmin_client", return_value=mock_garmin_client),
            pytest.raises(ValueError, match="No activities found"),
        ):
            worker._resolve_activity_id_from_api(date)


class TestProcessActivityByDateDelegation:
    """Tests for process_activity_by_date() delegation to process_activity()."""

    @pytest.mark.unit
    def test_process_activity_by_date_delegation(self, worker):
        """Test that process_activity_by_date delegates to process_activity correctly."""
        # Arrange
        date = "2025-10-05"
        activity_id = 20594901208
        expected_result = {
            "activity_id": activity_id,
            "performance_file": "/path/to/performance.json",
        }

        # Mock the resolver and process_activity
        with (
            patch.object(
                worker, "_resolve_activity_id_from_duckdb", return_value=activity_id
            ),
            patch.object(
                worker, "process_activity", return_value=expected_result
            ) as mock_process,
        ):
            # Act
            result = worker.process_activity_by_date(date)

            # Assert
            assert result == expected_result
            mock_process.assert_called_once_with(activity_id, date)

    @pytest.mark.unit
    def test_process_activity_by_date_api_fallback(self, worker):
        """Test that process_activity_by_date falls back to API when DuckDB returns None."""
        # Arrange
        date = "2025-10-05"
        activity_id = 20594901208
        expected_result = {
            "activity_id": activity_id,
            "performance_file": "/path/to/performance.json",
        }

        # Mock DuckDB to return None, API to return activity_id
        with (
            patch.object(worker, "_resolve_activity_id_from_duckdb", return_value=None),
            patch.object(
                worker, "_resolve_activity_id_from_api", return_value=activity_id
            ),
            patch.object(
                worker, "process_activity", return_value=expected_result
            ) as mock_process,
        ):
            # Act
            result = worker.process_activity_by_date(date)

            # Assert
            assert result == expected_result
            mock_process.assert_called_once_with(activity_id, date)
