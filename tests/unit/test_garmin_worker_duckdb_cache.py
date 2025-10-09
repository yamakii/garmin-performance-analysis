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
        """Test DuckDB cache check when all sections exist."""
        # Arrange
        activity_id = 12345678

        # Mock all sections to return data
        mock_db_reader.get_performance_section.side_effect = lambda aid, section: {
            "basic_metrics": {"distance": 10.0, "time": 3600},
            "heart_rate_zones": {"zone1": 30, "zone2": 40},
            "efficiency_metrics": {"cadence_stability": 0.95},
            "training_effect": {"aerobic": 3.5, "anaerobic": 2.0},
            "power_to_weight": {"avg_w_per_kg": 3.2},
            "split_metrics": [{"split": 1, "pace": 360}],
            "vo2_max": {"value": 55},
            "lactate_threshold": {"hr": 165},
            "form_efficiency_summary": {"gct_avg": 250},
            "hr_efficiency_analysis": {"zone_distribution": {}},
            "performance_trends": {"pace_consistency": 0.05},
        }.get(section)

        worker._db_reader = mock_db_reader

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        assert result is not None
        assert "basic_metrics" in result
        assert "heart_rate_zones" in result
        assert "efficiency_metrics" in result
        assert "training_effect" in result
        assert "power_to_weight" in result
        assert "split_metrics" in result
        assert "vo2_max" in result
        assert "lactate_threshold" in result
        assert "form_efficiency_summary" in result
        assert "hr_efficiency_analysis" in result
        assert "performance_trends" in result

        # Verify all sections were queried
        assert mock_db_reader.get_performance_section.call_count == 11

    @pytest.mark.unit
    def test_check_duckdb_cache_partial(self, worker, mock_db_reader):
        """Test DuckDB cache check when only some sections exist."""
        # Arrange
        activity_id = 12345678

        # Mock some sections to return None (missing)
        def mock_get_section(aid, section):
            if section in ["basic_metrics", "heart_rate_zones"]:
                return {"data": "exists"}
            return None

        mock_db_reader.get_performance_section.side_effect = mock_get_section
        worker._db_reader = mock_db_reader

        # Act
        result = worker._check_duckdb_cache(activity_id)

        # Assert
        assert result is None  # Should return None when not all sections exist

    @pytest.mark.unit
    def test_check_duckdb_cache_missing(self, worker, mock_db_reader):
        """Test DuckDB cache check when no data exists."""
        # Arrange
        activity_id = 12345678

        # Mock all sections to return None
        mock_db_reader.get_performance_section.return_value = None
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
