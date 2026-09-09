"""GarminIngestWorker.process_activity(): pipeline, partial status, completeness, full integration, force-refetch validation."""

import json
from unittest.mock import patch

import pytest


class TestProcessActivity:
    @pytest.mark.unit
    def test_save_data_creates_files(self, worker, sample_raw_data, tmp_path):
        """Test save_data creates required files (DuckDB insertion only)."""
        worker.raw_dir = tmp_path

        result = worker.save_data(
            20464005432, sample_raw_data, activity_date="2025-09-22"
        )

        # Verify result contains file paths (performance.json and precheck.json removed)
        assert "raw_dir" in result
        assert "parquet_file" not in result  # Parquet generation removed
        assert "performance_file" not in result  # Performance.json generation removed
        assert "precheck_file" not in result  # Precheck.json generation removed

    @pytest.mark.unit
    def test_process_activity_full_pipeline(self, worker):
        """Test process_activity executes full pipeline."""
        with (
            patch.object(worker, "collect_data") as mock_collect,
            patch.object(worker, "save_data") as mock_save,
        ):
            # Setup mocks
            mock_collect.return_value = {
                "activity": {},
                "splits": {"lapDTOs": []},
            }
            mock_save.return_value = {
                "activity_id": 12345,
                "date": "2025-09-22",
            }

            result = worker.process_activity(12345, "2025-09-22")

            # Verify all steps were called
            mock_collect.assert_called_once_with(12345, force_refetch=None)
            mock_save.assert_called_once()

            assert result["activity_id"] == 12345
            assert result["date"] == "2025-09-22"

    @pytest.mark.unit
    def test_process_activity_partial_status_on_failed_fetch(self, worker):
        """A failed per-API fetch surfaces as status='partial' + missing list."""
        with (
            patch.object(worker, "collect_data") as mock_collect,
            patch.object(worker, "_calculate_median_weight", return_value=None),
            patch.object(worker, "save_data") as mock_save,
        ):
            mock_collect.return_value = {
                "activity": {},
                "splits": None,
                "fetch_status": {
                    "activity_basic": "fetched",
                    "splits": "failed",
                    "weather": "fetched",
                },
            }
            mock_save.return_value = {"raw_dir": "/tmp/x"}

            result = worker.process_activity(12345, "2025-09-22")

            assert result["status"] == "partial"
            assert result["completeness"]["missing"] == ["splits"]
            assert result["completeness"]["fetch_status"]["splits"] == "failed"

    @pytest.mark.unit
    def test_process_activity_success_when_all_fetched(self, worker):
        """No failed fetch → status='success' and empty missing list."""
        with (
            patch.object(worker, "collect_data") as mock_collect,
            patch.object(worker, "_calculate_median_weight", return_value=None),
            patch.object(worker, "save_data") as mock_save,
        ):
            mock_collect.return_value = {
                "activity": {},
                "splits": {"lapDTOs": []},
                "fetch_status": {
                    "activity_basic": "fetched",
                    "splits": "cached",
                    "weather": "marker",
                },
            }
            mock_save.return_value = {"raw_dir": "/tmp/x"}

            result = worker.process_activity(12345, "2025-09-22")

            assert result["status"] == "success"
            assert result["completeness"]["missing"] == []

    @pytest.mark.integration
    def test_ingest_result_includes_completeness(self, worker, tmp_path):
        """End-to-end (cached API + mocked DuckDB) → result carries completeness.

        The returned dict must include ``completeness`` (with ``missing`` and
        ``fetch_status``) and remain JSON serializable across the MCP boundary.
        """
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)
        worker.raw_dir = tmp_path

        cache_files = {
            "activity.json": {"activityId": activity_id, "summaryDTO": {}},
            "activity_details.json": {"activityId": activity_id},
            "splits.json": {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            "weather.json": {"temp": 20},
            "gear.json": [{"customMakeModel": "Cached Shoes"}],
            "hr_zones.json": [{"zoneNumber": 1, "zoneLowBoundary": 100}],
            "vo2_max.json": {"vo2MaxValue": 47.0},
            "lactate_threshold.json": {"lactateThresholdBPM": 160},
        }
        for filename, data in cache_files.items():
            with open(activity_dir / filename, "w", encoding="utf-8") as f:
                json.dump(data, f)

        with (
            patch.object(worker, "_calculate_median_weight", return_value=None),
            patch.object(worker, "save_data", return_value={"raw_dir": str(tmp_path)}),
        ):
            result = worker.process_activity(activity_id, "2025-09-22")

        assert "completeness" in result
        assert result["completeness"]["missing"] == []
        assert isinstance(result["completeness"]["fetch_status"], dict)
        assert result["completeness"]["fetch_status"]  # non-empty
        assert result["status"] == "success"
        # Must survive JSON serialization at the MCP boundary.
        json.dumps(result)

    @pytest.mark.garmin_api
    def test_process_activity_full_integration(self, worker):
        """Test full process_activity pipeline with real data."""
        # Use existing cached activity
        activity_id = 20594901208
        date = "2025-10-05"

        # Execute full pipeline
        result = worker.process_activity(activity_id, date)

        # Verify result structure
        assert result["activity_id"] == activity_id
        assert result["date"] == date
        assert result["status"] == "success"
        assert "files" in result

        # Verify files were created (DuckDB-first architecture)
        files = result["files"]
        assert "raw_dir" in files  # Raw files in directory structure
        assert "parquet_file" not in files  # Parquet generation removed
        assert "performance_file" not in files  # Performance.json generation removed
        assert "precheck_file" not in files  # Precheck.json generation removed

        # Verify raw data directory exists
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        assert activity_dir.exists()

        # Verify individual raw JSON files exist
        assert (activity_dir / "activity.json").exists()
        assert (activity_dir / "splits.json").exists()
        assert (activity_dir / "weather.json").exists()

    @pytest.mark.unit
    def test_force_refetch_validation(self, worker):
        """Test force_refetch validation raises ValueError for invalid file names."""
        activity_id = 12345

        # Execute with invalid force_refetch value
        with pytest.raises(ValueError, match="Unsupported force_refetch files"):
            worker.collect_data(activity_id, force_refetch=["invalid_file"])

        # Execute with mix of valid and invalid
        with pytest.raises(ValueError, match="Unsupported force_refetch files"):
            worker.collect_data(
                activity_id, force_refetch=["weather", "invalid_file", "unknown"]
            )

    @pytest.mark.integration
    def test_process_activity_force_refetch_integration(self, worker, tmp_path):
        """Test process_activity passes force_refetch to collect_data."""
        activity_id = 12345
        date = "2025-10-10"

        # Mock collect_data to verify force_refetch is passed
        with patch.object(worker, "collect_data") as mock_collect:
            mock_collect.return_value = {
                "activity": {"activityId": activity_id},
                "activity_basic": {"summaryDTO": {}},
                "splits": {"lapDTOs": []},
                "weather": {},
                "gear": [],
                "hr_zones": [],
                "vo2_max": {},
                "lactate_threshold": {},
                "training_effect": {},
                "weight": None,
            }

            with patch.object(worker, "save_data") as mock_save:
                mock_save.return_value = {"activity_id": activity_id}

                # Execute with force_refetch
                worker.process_activity(
                    activity_id, date, force_refetch=["activity_details"]
                )

                # Verify collect_data was called with force_refetch
                mock_collect.assert_called_once_with(
                    activity_id, force_refetch=["activity_details"]
                )
