"""
Integration tests for GarminIngestWorker.process_activity().

Tests that process_activity() collects raw data as its first step.
"""

from unittest.mock import patch

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance for testing."""
    return GarminIngestWorker()


class TestProcessActivityDuckDBIntegration:
    """Tests for process_activity() raw-data collection flow."""

    @pytest.mark.integration
    def test_process_activity_falls_back_to_raw_data(self, worker):
        """Test that process_activity() collects raw_data as the first step."""
        # Arrange
        activity_id = 12345678
        date = "2025-10-09"

        # Mock collect_data to avoid API calls
        with patch.object(worker, "collect_data") as mock_collect_data:
            # Stop processing right after the first step
            mock_collect_data.side_effect = Exception(
                "Expected: collect_data() is the first step"
            )

            # Act & Assert
            with pytest.raises(Exception, match="Expected: collect_data"):
                worker.process_activity(activity_id, date)

            # Verify collect_data was called as the first step
            mock_collect_data.assert_called_once_with(activity_id, force_refetch=None)
