"""
Unit tests for GarminIngestWorker Phase 4: Table filtering in save_data.

Tests the table filtering logic:
- _should_insert_table(table_name, tables) method
- save_data() conditional insertion based on tables parameter
"""

from unittest.mock import patch

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance for testing."""
    return GarminIngestWorker()


@pytest.fixture
def mock_raw_data():
    """Create mock raw data for testing."""
    return {
        "activity": {"activityId": 12345},
        "splits": {"lapDTOs": []},
        "weather": {"temp": 20},
    }


class TestShouldInsertTable:
    """Tests for _should_insert_table() method."""

    @pytest.mark.unit
    def test_should_insert_table_no_filter(self, worker):
        """Test that all tables are inserted when tables=None."""
        # Arrange
        table_name = "splits"
        tables = None

        # Act
        result = worker._should_insert_table(table_name, tables)

        # Assert
        assert result is True

    @pytest.mark.unit
    def test_should_insert_table_in_filter(self, worker):
        """Test that table is inserted when it's in the filter list."""
        # Arrange
        table_name = "splits"
        tables = ["splits", "form_efficiency"]

        # Act
        result = worker._should_insert_table(table_name, tables)

        # Assert
        assert result is True

    @pytest.mark.unit
    def test_should_insert_table_not_in_filter(self, worker):
        """Test that table is NOT inserted when it's not in the filter list."""
        # Arrange
        table_name = "vo2_max"
        tables = ["splits", "form_efficiency"]

        # Act
        result = worker._should_insert_table(table_name, tables)

        # Assert
        assert result is False

    @pytest.mark.unit
    def test_should_insert_table_single_table_filter(self, worker):
        """Test filtering with single table in list."""
        # Arrange
        tables = ["activities"]

        # Act & Assert
        assert worker._should_insert_table("activities", tables) is True
        assert worker._should_insert_table("splits", tables) is False
        assert worker._should_insert_table("vo2_max", tables) is False


class TestSaveDataTableFiltering:
    """Tests for save_data() method with table filtering."""

    @pytest.mark.unit
    def test_save_data_with_no_filter_inserts_all_tables(self, worker, mock_raw_data):
        """Test that save_data inserts all tables when tables=None."""
        # Arrange
        activity_id = 12345
        activity_date = "2025-01-01"
        tables = None

        # Mock DuckDB connection (CRITICAL: prevent production DB access)
        from unittest.mock import MagicMock

        mock_conn = MagicMock()

        # Mock all inserter functions (they're imported inside save_data)
        with (
            patch("duckdb.connect") as mock_duckdb_connect,
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form_eff,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf_trends,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lactate,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
        ):
            # Configure DuckDB connection mock
            mock_duckdb_connect.return_value.__enter__.return_value = mock_conn

            # Configure all mocks to return True
            for mock in [
                mock_activities,
                mock_splits,
                mock_form_eff,
                mock_hr_zones,
                mock_hr_eff,
                mock_perf_trends,
                mock_lactate,
                mock_vo2,
            ]:
                mock.return_value = True

            # Act
            worker.save_data(activity_id, mock_raw_data, activity_date, tables)

            # Assert - all inserters should be called
            mock_activities.assert_called_once()
            mock_splits.assert_called_once()
            mock_form_eff.assert_called_once()
            mock_hr_zones.assert_called_once()
            mock_hr_eff.assert_called_once()
            mock_perf_trends.assert_called_once()
            mock_lactate.assert_called_once()
            mock_vo2.assert_called_once()
            # time_series is conditional on file existence, not tested here
            # time_series is conditional on file existence, not tested here

    @pytest.mark.unit
    def test_save_data_with_single_table_filter_only_inserts_specified(
        self, worker, mock_raw_data
    ):
        """Test that save_data only inserts specified table."""
        # Arrange
        activity_id = 12345
        activity_date = "2025-01-01"
        tables = ["splits"]

        # Mock DuckDB connection (CRITICAL: prevent production DB access)
        from unittest.mock import MagicMock

        mock_conn = MagicMock()

        # Mock all inserter functions
        with (
            patch("duckdb.connect") as mock_duckdb_connect,
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form_eff,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf_trends,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lactate,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
        ):
            # Configure DuckDB connection mock
            mock_duckdb_connect.return_value.__enter__.return_value = mock_conn

            mock_splits.return_value = True

            # Act
            worker.save_data(activity_id, mock_raw_data, activity_date, tables)

            # Assert - only splits should be called
            mock_activities.assert_not_called()
            mock_splits.assert_called_once()
            mock_form_eff.assert_not_called()
            mock_hr_zones.assert_not_called()
            mock_hr_eff.assert_not_called()
            mock_perf_trends.assert_not_called()
            mock_lactate.assert_not_called()
            mock_vo2.assert_not_called()

    @pytest.mark.unit
    def test_save_data_with_multiple_table_filter_inserts_specified(
        self, worker, mock_raw_data
    ):
        """Test that save_data inserts multiple specified tables."""
        # Arrange
        activity_id = 12345
        activity_date = "2025-01-01"
        tables = ["splits", "form_efficiency", "vo2_max"]

        # Mock DuckDB connection (CRITICAL: prevent production DB access)
        from unittest.mock import MagicMock

        mock_conn = MagicMock()

        # Mock all inserter functions
        with (
            patch("duckdb.connect") as mock_duckdb_connect,
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form_eff,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf_trends,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lactate,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
        ):
            # Configure DuckDB connection mock
            mock_duckdb_connect.return_value.__enter__.return_value = mock_conn

            # Configure specified mocks to return True
            mock_splits.return_value = True
            mock_form_eff.return_value = True
            mock_vo2.return_value = True

            # Act
            worker.save_data(activity_id, mock_raw_data, activity_date, tables)

            # Assert - only specified tables should be called
            mock_activities.assert_not_called()
            mock_splits.assert_called_once()
            mock_form_eff.assert_called_once()
            mock_hr_zones.assert_not_called()
            mock_hr_eff.assert_not_called()
            mock_perf_trends.assert_not_called()
            mock_lactate.assert_not_called()
            mock_vo2.assert_called_once()

    @pytest.mark.unit
    def test_save_data_with_activities_table_filter(self, worker, mock_raw_data):
        """Test that save_data can filter activities table specifically."""
        # Arrange
        activity_id = 12345
        activity_date = "2025-01-01"
        tables = ["activities"]

        # Mock DuckDB connection (CRITICAL: prevent production DB access)
        from unittest.mock import MagicMock

        mock_conn = MagicMock()

        # Mock inserter functions
        with (
            patch("duckdb.connect") as mock_duckdb_connect,
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form_eff,
        ):
            # Configure DuckDB connection mock
            mock_duckdb_connect.return_value.__enter__.return_value = mock_conn

            mock_activities.return_value = True

            # Act
            worker.save_data(activity_id, mock_raw_data, activity_date, tables)

            # Assert - only activities should be called
            mock_activities.assert_called_once()
            mock_splits.assert_not_called()
            mock_form_eff.assert_not_called()


class TestProcessActivityTableFilteringIntegration:
    """Integration tests for process_activity with tables parameter."""

    @pytest.mark.unit
    def test_process_activity_passes_tables_to_save_data(self, worker):
        """Test that process_activity passes tables parameter to save_data."""
        # Arrange
        activity_id = 12345
        date = "2025-01-01"
        tables = ["splits", "form_efficiency"]

        # Mock methods
        with (
            patch.object(worker, "_check_duckdb_cache", return_value=None),
            patch.object(worker, "collect_data", return_value={}),
            patch.object(worker, "_calculate_median_weight", return_value=None),
            patch.object(worker, "save_data") as mock_save_data,
        ):
            # Act
            worker.process_activity(activity_id, date, tables=tables)

            # Assert - save_data should be called with tables parameter
            mock_save_data.assert_called_once()
            call_args = mock_save_data.call_args
            assert call_args[1]["tables"] == tables
