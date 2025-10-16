"""
Integration tests for GarminIngestWorker time series metrics insertion.

Phase 2: Integration with save_data()
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


class TestGarminWorkerTimeSeriesIntegration:
    """Test suite for TimeSeriesMetricsInserter integration in GarminIngestWorker."""

    @pytest.fixture
    def worker(self, tmp_path):
        """Create GarminIngestWorker instance with temporary paths."""
        worker = GarminIngestWorker(db_path=str(tmp_path / "test.duckdb"))
        worker.raw_dir = tmp_path / "raw"
        worker.performance_dir = tmp_path / "performance"
        worker.precheck_dir = tmp_path / "precheck"
        worker.raw_dir.mkdir(parents=True)
        worker.performance_dir.mkdir(parents=True)
        worker.precheck_dir.mkdir(parents=True)
        return worker

    @pytest.fixture
    def sample_activity_details(self):
        """Sample activity_details.json content."""
        return {
            "activityId": 12345,
            "metricDescriptors": [
                {"key": "sumDuration", "metricsIndex": 0, "unit": {"factor": 1000.0}},
                {"key": "directHeartRate", "metricsIndex": 1, "unit": {"factor": 1.0}},
                {"key": "directSpeed", "metricsIndex": 2, "unit": {"factor": 0.1}},
                {
                    "key": "directElevation",
                    "metricsIndex": 3,
                    "unit": {"factor": 100.0},
                },
            ],
            "activityDetailMetrics": [
                {
                    "metrics": [0, 120, 30, 5000]
                },  # timestamp_s=0, HR=120, speed=3.0 m/s, elevation=50.0m
                {"metrics": [1000, 125, 32, 5100]},  # timestamp_s=1
                {"metrics": [2000, 130, 34, 5200]},  # timestamp_s=2
            ],
        }

    @pytest.mark.unit
    def test_save_data_with_time_series(
        self, worker, sample_activity_details, tmp_path
    ):
        """Test save_data() calls insert_time_series_metrics when activity_details.json exists."""
        # Setup: Create activity_details.json
        activity_id = 12345
        activity_dir = tmp_path / "raw" / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        activity_details_file = activity_dir / "activity_details.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(sample_activity_details, f)

        # Setup: Create required raw data files
        (activity_dir / "activity.json").write_text("{}")
        (activity_dir / "splits.json").write_text('{"lapDTOs": []}')
        (activity_dir / "weather.json").write_text("{}")
        (activity_dir / "gear.json").write_text("[]")

        # Mock inserters to avoid actual DB operations
        # Note: Patch where functions are used (inside save_data), not where they're defined
        with (
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lt,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
            patch(
                "tools.database.inserters.time_series_metrics.insert_time_series_metrics"
            ) as mock_time_series,
        ):
            # Mock all inserters as successful
            mock_activities.return_value = True
            mock_splits.return_value = True
            mock_form.return_value = True
            mock_hr_zones.return_value = True
            mock_hr_eff.return_value = True
            mock_perf.return_value = True
            mock_lt.return_value = True
            mock_vo2.return_value = True
            mock_time_series.return_value = True

            # Prepare sample data
            import pandas as pd

            df = pd.DataFrame({"split_number": [1], "avg_heart_rate": [120]})
            raw_data: dict[str, Any] = {"activity": {}}

            # Execute
            worker.save_data(activity_id, raw_data, df, activity_date="2025-10-13")

            # Verify: insert_time_series_metrics was called
            mock_time_series.assert_called_once()
            call_args = mock_time_series.call_args
            assert call_args[1]["activity_id"] == activity_id
            assert call_args[1]["activity_details_file"] == str(activity_details_file)

    @pytest.mark.unit
    def test_save_data_missing_activity_details(self, worker, tmp_path):
        """Test save_data() handles missing activity_details.json gracefully (WARNING log, no error)."""
        # Setup: Activity directory WITHOUT activity_details.json
        activity_id = 12345
        activity_dir = tmp_path / "raw" / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        # Create required files (but NOT activity_details.json)
        (activity_dir / "activity.json").write_text("{}")
        (activity_dir / "splits.json").write_text('{"lapDTOs": []}')
        (activity_dir / "weather.json").write_text("{}")
        (activity_dir / "gear.json").write_text("[]")

        # Mock inserters
        with (
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lt,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
            patch(
                "tools.database.inserters.time_series_metrics.insert_time_series_metrics"
            ) as mock_time_series,
            patch("tools.ingest.garmin_worker.logger") as mock_logger,
        ):
            mock_activities.return_value = True
            mock_splits.return_value = True
            mock_form.return_value = True
            mock_hr_zones.return_value = True
            mock_hr_eff.return_value = True
            mock_perf.return_value = True
            mock_lt.return_value = True
            mock_vo2.return_value = True

            # Prepare sample data
            import pandas as pd

            df = pd.DataFrame({"split_number": [1], "avg_heart_rate": [120]})
            raw_data: dict[str, Any] = {"activity": {}}

            # Execute - should NOT raise exception
            result = worker.save_data(
                activity_id, raw_data, df, activity_date="2025-10-13"
            )

            # Verify: insert_time_series_metrics was NOT called
            mock_time_series.assert_not_called()

            # Verify: WARNING log was generated
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "activity_details.json not found" in str(call)
            ]
            assert (
                len(warning_calls) > 0
            ), "Expected WARNING log for missing activity_details.json"

            # Verify: save_data still returns file paths (pipeline continues)
            assert "precheck_file" in result

    @pytest.mark.unit
    def test_save_data_time_series_insertion_failure(
        self, worker, sample_activity_details, tmp_path
    ):
        """Test save_data() handles time series insertion failure gracefully (logs error, continues)."""
        # Setup: Create activity_details.json
        activity_id = 12345
        activity_dir = tmp_path / "raw" / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        activity_details_file = activity_dir / "activity_details.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(sample_activity_details, f)

        # Create required files
        (activity_dir / "activity.json").write_text("{}")
        (activity_dir / "splits.json").write_text('{"lapDTOs": []}')
        (activity_dir / "weather.json").write_text("{}")
        (activity_dir / "gear.json").write_text("[]")

        # Mock inserters with time_series failing
        with (
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lt,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
            patch(
                "tools.database.inserters.time_series_metrics.insert_time_series_metrics"
            ) as mock_time_series,
            patch("tools.ingest.garmin_worker.logger") as mock_logger,
        ):
            mock_activities.return_value = True
            mock_splits.return_value = True
            mock_form.return_value = True
            mock_hr_zones.return_value = True
            mock_hr_eff.return_value = True
            mock_perf.return_value = True
            mock_lt.return_value = True
            mock_vo2.return_value = True

            # Time series insertion fails
            mock_time_series.return_value = False

            # Prepare sample data
            import pandas as pd

            df = pd.DataFrame({"split_number": [1], "avg_heart_rate": [120]})
            raw_data: dict[str, Any] = {"activity": {}}

            # Execute - should NOT raise exception
            result = worker.save_data(
                activity_id, raw_data, df, activity_date="2025-10-13"
            )

            # Verify: insert_time_series_metrics was called
            mock_time_series.assert_called_once()

            # Verify: ERROR log was generated (match exact text from implementation)
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "Failed to insert time_series_metrics to DuckDB" in str(call)
            ]
            assert len(error_calls) > 0, "Expected ERROR log for insertion failure"

            # Verify: save_data still returns file paths (pipeline continues)
            assert "precheck_file" in result

    @pytest.mark.integration
    def test_save_data_with_real_fixture(self, worker):
        """Integration test with real test fixture from tests/fixtures."""
        # Use existing test fixture
        fixture_path = Path("tests/fixtures/data/raw/activity/12345678901")
        if not fixture_path.exists():
            pytest.skip("Test fixture not found")

        activity_id = 12345678901
        activity_details_file = fixture_path / "activity_details.json"

        if not activity_details_file.exists():
            pytest.skip("activity_details.json fixture not found")

        # Mock inserters but use real file
        with (
            patch(
                "tools.database.inserters.activities.insert_activities"
            ) as mock_activities,
            patch("tools.database.inserters.splits.insert_splits") as mock_splits,
            patch(
                "tools.database.inserters.form_efficiency.insert_form_efficiency"
            ) as mock_form,
            patch(
                "tools.database.inserters.heart_rate_zones.insert_heart_rate_zones"
            ) as mock_hr_zones,
            patch(
                "tools.database.inserters.hr_efficiency.insert_hr_efficiency"
            ) as mock_hr_eff,
            patch(
                "tools.database.inserters.performance_trends.insert_performance_trends"
            ) as mock_perf,
            patch(
                "tools.database.inserters.lactate_threshold.insert_lactate_threshold"
            ) as mock_lt,
            patch("tools.database.inserters.vo2_max.insert_vo2_max") as mock_vo2,
            patch(
                "tools.database.inserters.time_series_metrics.insert_time_series_metrics"
            ) as mock_time_series,
        ):
            mock_activities.return_value = True
            mock_splits.return_value = True
            mock_form.return_value = True
            mock_hr_zones.return_value = True
            mock_hr_eff.return_value = True
            mock_perf.return_value = True
            mock_lt.return_value = True
            mock_vo2.return_value = True
            mock_time_series.return_value = True

            # Prepare minimal data
            import pandas as pd

            df = pd.DataFrame({"split_number": [1], "avg_heart_rate": [120]})
            raw_data: dict[str, Any] = {"activity": {}}

            # Update worker paths to use fixture
            worker.raw_dir = Path("tests/fixtures/data/raw")

            # Execute
            worker.save_data(activity_id, raw_data, df, activity_date="2025-10-13")

            # Verify: insert_time_series_metrics was called with real fixture
            mock_time_series.assert_called_once()
            call_args = mock_time_series.call_args
            assert "activity_details.json" in str(call_args[1]["activity_details_file"])
