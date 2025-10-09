"""
Unit tests for GarminIngestWorker Phase 0: Per-API cache implementation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker_with_temp_dirs(tmp_path, monkeypatch):
    """Create GarminIngestWorker with temporary directories."""

    def patched_init(self, db_path=None):
        self.project_root = tmp_path
        self.raw_dir = tmp_path / "raw"
        self.parquet_dir = tmp_path / "parquet"
        self.performance_dir = tmp_path / "performance"
        self.precheck_dir = tmp_path / "precheck"
        self.weight_cache_dir = tmp_path / "weight_cache" / "raw"

        # Create directories
        for directory in [
            self.raw_dir,
            self.parquet_dir,
            self.performance_dir,
            self.precheck_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        self._db_reader = None
        self._db_path = db_path
        self._garmin_client = None

    monkeypatch.setattr(GarminIngestWorker, "__init__", patched_init)

    worker = GarminIngestWorker()
    return worker


@pytest.fixture
def sample_api_responses():
    """Sample API responses for each endpoint."""
    return {
        "activity": {
            "activityId": 20594901208,
            "activityName": "Morning Run",
            "summaryDTO": {
                "activityId": 20594901208,
                "trainingEffect": 2.4,
                "anaerobicTrainingEffect": 0.0,
                "startTimeLocal": "2025-09-22T06:00:00.0",
            },
        },
        "activity_details": {
            "summaryDTO": {
                "activityId": 20594901208,
                "trainingEffect": 2.4,
                "anaerobicTrainingEffect": 0.0,
                "startTimeLocal": "2025-09-22T06:00:00.0",
            }
        },
        "splits": {"lapDTOs": [{"lapIndex": 1, "distance": 1000}]},
        "weather": {"temp": 20, "apparentTemp": 18},
        "gear": [{"gearId": "123", "gearName": "Nike Pegasus"}],
        "hr_zones": [{"zoneNumber": 1, "secsInZone": 100}],
        "vo2_max": {"vo2MaxValue": 50, "vo2MaxPreciseValue": 50.5},
        "lactate_threshold": {"speed_and_heart_rate": {"heartRate": 160, "speed": 3.5}},
    }


class TestCollectDataPerAPICache:
    """Test per-API caching in collect_data method."""

    @patch("tools.ingest.garmin_worker.GarminIngestWorker.get_garmin_client")
    def test_collect_data_all_apis_cached(
        self, mock_get_client, worker_with_temp_dirs, sample_api_responses
    ):
        """Test when all API responses are cached."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Create cached API files
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        api_files = {
            "activity.json": sample_api_responses["activity"],
            "activity_details.json": sample_api_responses["activity_details"],
            "splits.json": sample_api_responses["splits"],
            "weather.json": sample_api_responses["weather"],
            "gear.json": sample_api_responses["gear"],
            "hr_zones.json": sample_api_responses["hr_zones"],
            "vo2_max.json": sample_api_responses["vo2_max"],
            "lactate_threshold.json": sample_api_responses["lactate_threshold"],
        }

        for file_name, data in api_files.items():
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute collect_data
        raw_data = worker.collect_data(activity_id)

        # Verify no API calls were made
        mock_get_client.assert_not_called()

        # Verify returned data structure
        assert raw_data["activity_basic"] == sample_api_responses["activity"]
        assert raw_data["activity"] == sample_api_responses["activity_details"]
        assert raw_data["splits"] == sample_api_responses["splits"]
        assert raw_data["weather"] == sample_api_responses["weather"]

    @patch("tools.ingest.garmin_worker.GarminIngestWorker.get_garmin_client")
    def test_collect_data_partial_cache_fetch_missing(
        self, mock_get_client, worker_with_temp_dirs, sample_api_responses
    ):
        """Test when some APIs are cached, others need fetching."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Create partial cache (only activity_details and splits)
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        with open(activity_dir / "activity_details.json", "w", encoding="utf-8") as f:
            json.dump(sample_api_responses["activity_details"], f)

        with open(activity_dir / "splits.json", "w", encoding="utf-8") as f:
            json.dump(sample_api_responses["splits"], f)

        # Mock Garmin client
        mock_client = MagicMock()
        mock_client.get_activity_weather.return_value = sample_api_responses["weather"]
        mock_client.get_activity_gear.return_value = sample_api_responses["gear"]
        mock_client.get_activity_hr_in_timezones.return_value = sample_api_responses[
            "hr_zones"
        ]
        mock_client.get_max_metrics.return_value = {
            "generic": sample_api_responses["vo2_max"]
        }
        mock_client.get_lactate_threshold.return_value = sample_api_responses[
            "lactate_threshold"
        ]
        mock_get_client.return_value = mock_client

        # Execute collect_data
        raw_data = worker.collect_data(activity_id)

        # Verify API calls were made for missing data
        mock_client.get_activity_weather.assert_called_once_with(activity_id)
        mock_client.get_activity_gear.assert_called_once_with(activity_id)
        mock_client.get_activity_hr_in_timezones.assert_called_once_with(activity_id)

        # Verify all files now exist
        assert (activity_dir / "weather.json").exists()
        assert (activity_dir / "gear.json").exists()
        assert raw_data["weather"] == sample_api_responses["weather"]
        assert (activity_dir / "hr_zones.json").exists()

    @patch("tools.ingest.garmin_worker.GarminIngestWorker.get_garmin_client")
    def test_collect_data_no_cache_fetch_all(
        self, mock_get_client, worker_with_temp_dirs, sample_api_responses
    ):
        """Test when no cache exists, fetch all from API."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Mock Garmin client
        mock_client = MagicMock()
        mock_client.get_activity_details.return_value = sample_api_responses[
            "activity_details"
        ]
        mock_client.get_activity_splits.return_value = sample_api_responses["splits"]
        mock_client.get_activity_weather.return_value = sample_api_responses["weather"]
        mock_client.get_activity_gear.return_value = sample_api_responses["gear"]
        mock_client.get_activity_hr_in_timezones.return_value = sample_api_responses[
            "hr_zones"
        ]
        mock_client.get_max_metrics.return_value = {
            "generic": sample_api_responses["vo2_max"]
        }
        mock_client.get_lactate_threshold.return_value = sample_api_responses[
            "lactate_threshold"
        ]
        mock_get_client.return_value = mock_client

        # Execute collect_data
        raw_data = worker.collect_data(activity_id)

        # Verify all API calls were made
        mock_client.get_activity_details.assert_called_once_with(
            activity_id, maxchart=2000
        )
        mock_client.get_activity_splits.assert_called_once_with(activity_id)
        mock_client.get_activity_weather.assert_called_once_with(activity_id)

        # Verify all files were created
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        assert activity_dir.exists()
        assert (activity_dir / "activity_details.json").exists()
        assert raw_data["activity"] == sample_api_responses["activity_details"]
        assert (activity_dir / "splits.json").exists()
        assert (activity_dir / "weather.json").exists()

    @patch("tools.ingest.garmin_worker.GarminIngestWorker.get_garmin_client")
    def test_collect_data_api_error_saves_partial(
        self, mock_get_client, worker_with_temp_dirs, sample_api_responses
    ):
        """Test that partial data is saved even if some APIs fail."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Mock Garmin client with one failing API
        mock_client = MagicMock()
        mock_client.get_activity_details.return_value = sample_api_responses[
            "activity_details"
        ]
        mock_client.get_activity_splits.return_value = sample_api_responses["splits"]
        mock_client.get_activity_weather.side_effect = Exception("Weather API failed")
        mock_client.get_activity_gear.return_value = sample_api_responses["gear"]
        mock_client.get_activity_hr_in_timezones.return_value = sample_api_responses[
            "hr_zones"
        ]
        mock_client.get_max_metrics.return_value = {
            "generic": sample_api_responses["vo2_max"]
        }
        mock_client.get_lactate_threshold.return_value = sample_api_responses[
            "lactate_threshold"
        ]
        mock_get_client.return_value = mock_client

        # Execute collect_data
        raw_data = worker.collect_data(activity_id)

        # Verify partial data was saved
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        assert (activity_dir / "activity_details.json").exists()
        assert (activity_dir / "splits.json").exists()
        assert not (activity_dir / "weather.json").exists()  # Failed API
        assert (activity_dir / "gear.json").exists()

        # Verify raw_data contains available data
        assert raw_data["activity"] is not None
        assert raw_data["splits"] is not None
        assert raw_data["weather"] is None  # Failed


class TestLoadFromCache:
    """Test load_from_cache method."""

    def test_load_from_cache_complete(
        self, worker_with_temp_dirs, sample_api_responses
    ):
        """Test loading complete cached data."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Create complete cache
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        api_files = {
            "activity.json": sample_api_responses["activity"],
            "activity_details.json": sample_api_responses["activity_details"],
            "splits.json": sample_api_responses["splits"],
            "weather.json": sample_api_responses["weather"],
            "gear.json": sample_api_responses["gear"],
            "hr_zones.json": sample_api_responses["hr_zones"],
            "vo2_max.json": sample_api_responses["vo2_max"],
            "lactate_threshold.json": sample_api_responses["lactate_threshold"],
        }

        for file_name, data in api_files.items():
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute load_from_cache
        raw_data = worker.load_from_cache(activity_id)

        # Verify complete data loaded
        assert raw_data is not None
        assert raw_data["activity_basic"] == sample_api_responses["activity"]
        assert raw_data["activity"] == sample_api_responses["activity_details"]
        assert raw_data["splits"] == sample_api_responses["splits"]
        assert raw_data["weather"] == sample_api_responses["weather"]

    def test_load_from_cache_partial_returns_none(
        self, worker_with_temp_dirs, sample_api_responses
    ):
        """Test that partial cache returns None."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Create partial cache (missing required files)
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        with open(activity_dir / "activity_details.json", "w", encoding="utf-8") as f:
            json.dump(sample_api_responses["activity_details"], f)

        # Execute load_from_cache
        raw_data = worker.load_from_cache(activity_id)

        # Should return None because cache is incomplete
        assert raw_data is None

    def test_load_from_cache_directory_not_exists(self, worker_with_temp_dirs):
        """Test when cache directory doesn't exist."""
        worker = worker_with_temp_dirs
        activity_id = 99999999999

        # Execute load_from_cache
        raw_data = worker.load_from_cache(activity_id)

        # Should return None
        assert raw_data is None

    def test_load_from_cache_with_training_effect_extraction(
        self, worker_with_temp_dirs, sample_api_responses
    ):
        """Test training_effect is extracted during load."""
        worker = worker_with_temp_dirs
        activity_id = 20594901208

        # Create cache without training_effect in separate file
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        api_files = {
            "activity.json": sample_api_responses["activity"],
            "activity_details.json": sample_api_responses["activity_details"],
            "splits.json": sample_api_responses["splits"],
            "weather.json": sample_api_responses["weather"],
            "gear.json": sample_api_responses["gear"],
            "hr_zones.json": sample_api_responses["hr_zones"],
            "vo2_max.json": sample_api_responses["vo2_max"],
            "lactate_threshold.json": sample_api_responses["lactate_threshold"],
        }

        for file_name, data in api_files.items():
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute load_from_cache
        raw_data = worker.load_from_cache(activity_id)

        # Verify training_effect was extracted from activity_basic.summaryDTO
        assert "training_effect" in raw_data
        assert raw_data["training_effect"]["aerobicTrainingEffect"] == 2.4
