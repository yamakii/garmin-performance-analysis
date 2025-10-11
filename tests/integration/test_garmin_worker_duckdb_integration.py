"""
Integration tests for GarminIngestWorker DuckDB cache integration.

Tests the process_activity() method's DuckDB cache-first behavior.
"""

from unittest.mock import patch

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance for testing."""
    return GarminIngestWorker()


class TestProcessActivityDuckDBIntegration:
    """Tests for process_activity() DuckDB cache integration."""

    @pytest.mark.integration
    def test_process_activity_uses_duckdb_cache(self, worker):
        """Test that process_activity() uses DuckDB cache when available."""
        # Arrange
        activity_id = 12345678
        date = "2025-10-09"

        # Mock _check_duckdb_cache to return complete data
        cached_performance_data = {
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
        }

        with patch.object(
            worker, "_check_duckdb_cache", return_value=cached_performance_data
        ):
            # Act
            result = worker.process_activity(activity_id, date)

            # Assert
            assert result["status"] == "success"
            assert result["source"] == "duckdb_cache"
            assert result["activity_id"] == activity_id
            assert result["date"] == date
            assert result["performance_data"] == cached_performance_data

    @pytest.mark.integration
    def test_process_activity_falls_back_to_raw_data(self, worker):
        """Test that process_activity() falls back to raw_data when DuckDB cache is incomplete."""
        # Arrange
        activity_id = 12345678
        date = "2025-10-09"

        # Mock _check_duckdb_cache to return None (incomplete cache)
        # Mock collect_data to avoid API calls
        with (
            patch.object(worker, "_check_duckdb_cache", return_value=None),
            patch.object(worker, "collect_data") as mock_collect_data,
        ):
            # Skip actual processing by mocking all subsequent steps
            mock_collect_data.side_effect = Exception(
                "Expected: Should fall back to collect_data()"
            )

            # Act & Assert
            with pytest.raises(Exception, match="Expected: Should fall back"):
                worker.process_activity(activity_id, date)

            # Verify collect_data was called (fallback happened)
            mock_collect_data.assert_called_once_with(activity_id, force_refetch=None)
