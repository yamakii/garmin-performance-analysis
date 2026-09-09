"""GarminIngestWorker.collect_data(): cache use, get_activity, force refetch, default behaviour, training-effect extraction."""

import json
from typing import Any
from unittest.mock import patch

import pytest


class TestCollectData:
    @pytest.mark.unit
    def test_collect_data_uses_cache_when_available(self, worker, tmp_path):
        """Test collect_data prioritizes cache over API calls."""
        # Setup: Create cached files in new per-file format
        worker.raw_dir = tmp_path
        activity_dir = tmp_path / "activity" / "12345"
        activity_dir.mkdir(parents=True)

        cache_files = {
            "activity.json": {"activityId": 12345, "summaryDTO": {}},
            "splits.json": {"activityId": 12345, "lapDTOs": [], "eventDTOs": []},
            "weather.json": {"temp": 20},
            "gear.json": [{"customMakeModel": "Cached Shoes"}],
            "hr_zones.json": [{"zoneNumber": 1, "zoneLowBoundary": 100}],
            "vo2_max.json": {},
            "lactate_threshold.json": {},
        }
        for filename, data in cache_files.items():
            with open(activity_dir / filename, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute
        result = worker.collect_data(12345)

        # Verify cache was used (not API)
        assert result["gear"][0]["customMakeModel"] == "Cached Shoes"
        assert "activity_basic" in result
        assert "splits" in result
        assert "weather" in result
        assert "gear" in result
        assert "hr_zones" in result

    @pytest.mark.garmin_api
    def test_collect_data_with_real_garmin_api(self, worker):
        """Test collect_data with real Garmin MCP connection."""
        # Use existing activity with cache to avoid API rate limit
        # This verifies cache-first strategy works with real file structure
        activity_id = 20594901208

        # Verify cache file exists (avoid API call)
        cache_file = worker.raw_dir / f"{activity_id}_raw.json"
        if not cache_file.exists():
            pytest.skip("Test requires cached activity data")

        # Execute
        result = worker.collect_data(activity_id)

        # Verify structure
        assert "activity" in result
        assert "splits" in result
        assert "weather" in result
        assert "gear" in result
        assert "hr_zones" in result

        # Verify activity data
        activity = result["activity"]
        assert "activityId" in activity
        assert activity["activityId"] == activity_id

        # Verify splits data
        splits = result["splits"]
        assert "lapDTOs" in splits
        assert len(splits["lapDTOs"]) > 0

    @pytest.mark.unit
    def test_collect_data_calls_get_activity(self, worker, tmp_path):
        """Test collect_data calls get_activity() API when activity.json is missing."""
        activity_id = 12345

        worker.raw_dir = tmp_path

        # DO NOT create activity directory - force complete cache miss
        # This will trigger API calls

        # Mock ALL API calls
        mock_activity_basic = {
            "activityId": activity_id,
            "activityName": "Test Run",
            "summaryDTO": {"trainingEffect": 4.0, "anaerobicTrainingEffect": 2.5},
        }

        mock_splits = {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []}
        mock_weather = {"temp": 20}
        mock_gear: list[dict] = []
        mock_hr_zones: list[dict] = []
        mock_vo2_max: dict[str, Any] = {}
        mock_lactate: dict[str, Any] = {}
        mock_activity_details = {"activityId": activity_id}

        with patch(
            "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client"
        ) as mock_client_fn:
            mock_client = mock_client_fn.return_value
            # Setup all API mocks
            mock_client.get_activity.return_value = mock_activity_basic
            mock_client.get_activity_details.return_value = mock_activity_details
            mock_client.get_activity_splits.return_value = mock_splits
            mock_client.get_activity_weather.return_value = mock_weather
            mock_client.get_activity_gear.return_value = mock_gear
            mock_client.get_activity_hr_in_timezones.return_value = mock_hr_zones
            mock_client.get_activity_vo2_max.return_value = mock_vo2_max
            mock_client.get_activity_lactate_threshold.return_value = mock_lactate
            mock_client.get_activity_evaluation.return_value = {}

            # Execute
            result = worker.collect_data(activity_id)

            # Verify get_activity() was called
            mock_client.get_activity.assert_called_once_with(str(activity_id))

            # Verify result
            assert "activity_basic" in result
            assert result["activity_basic"]["activityName"] == "Test Run"

            # Verify activity.json was created
            activity_dir = tmp_path / "activity" / str(activity_id)
            activity_json = activity_dir / "activity.json"
            assert activity_json.exists()

    @pytest.mark.unit
    def test_training_effect_extraction_from_activity_basic(self, worker, tmp_path):
        """Test training_effect extraction from activity_basic.summaryDTO."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create activity.json with full summaryDTO
        activity_basic_data = {
            "activityId": activity_id,
            "summaryDTO": {
                "trainingEffect": 3.8,
                "anaerobicTrainingEffect": 2.2,
                "aerobicTrainingEffectMessage": "Highly Improving",
                "anaerobicTrainingEffectMessage": "Improving",
                "trainingEffectLabel": "Highly Improving",
            },
        }
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic_data, f)

        # Create minimal other files
        for file_name, data in [
            ("activity_details.json", {"activityId": activity_id}),
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("weather.json", {}),
            ("gear.json", []),
            ("hr_zones.json", []),
            ("vo2_max.json", {}),
            ("lactate_threshold.json", {}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute
        result = worker.load_from_cache(activity_id)

        # Verify training_effect extraction
        assert result is not None
        assert "training_effect" in result
        training_effect = result["training_effect"]
        assert training_effect["aerobicTrainingEffect"] == 3.8
        assert training_effect["anaerobicTrainingEffect"] == 2.2
        assert training_effect["aerobicTrainingEffectMessage"] == "Highly Improving"
        assert training_effect["anaerobicTrainingEffectMessage"] == "Improving"
        assert training_effect["trainingEffectLabel"] == "Highly Improving"

    @pytest.mark.garmin_api
    def test_collect_data_with_get_activity_api(self, worker):
        """Test collect_data with real get_activity() API call.

        IMPORTANT:
        - Uses existing cached activity to avoid API rate limit
        - Verifies activity.json is created if missing
        - Run explicitly with: uv run pytest -m garmin_api
        """
        # Use existing cached activity
        activity_id = 20594901208

        # Delete activity.json to force API call (but keep other files for efficiency)
        activity_dir = worker.raw_dir / "activity" / str(activity_id)
        activity_json = activity_dir / "activity.json"

        # Backup if exists
        backup_path = None
        if activity_json.exists():
            backup_path = activity_json.with_suffix(".json.backup")
            activity_json.rename(backup_path)

        try:
            # Execute (should call get_activity() API)
            result = worker.collect_data(activity_id)

            # Verify structure
            assert "activity_basic" in result
            assert "activity" in result
            assert "training_effect" in result

            # Verify activity_basic content
            activity_basic = result["activity_basic"]
            assert activity_basic["activityId"] == activity_id
            assert "summaryDTO" in activity_basic

            # Verify training_effect extraction
            training_effect = result["training_effect"]
            assert "aerobicTrainingEffect" in training_effect
            assert "anaerobicTrainingEffect" in training_effect

            # Verify activity.json was created
            assert activity_json.exists()

        finally:
            # Restore backup
            if backup_path and backup_path.exists():
                if activity_json.exists():
                    activity_json.unlink()
                backup_path.rename(activity_json)

    @pytest.mark.unit
    def test_collect_data_force_refetch_single_file(self, worker, tmp_path):
        """Test force_refetch=['activity_details'] refetches only activity_details.json."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create full cache with OLD activity_details.json
        old_activity_details = {"activityId": activity_id, "maxchart": 2000}
        with open(activity_dir / "activity_details.json", "w", encoding="utf-8") as f:
            json.dump(old_activity_details, f)

        # Create activity.json (required)
        activity_basic = {
            "activityId": activity_id,
            "summaryDTO": {"duration": 3000, "trainingEffect": 3.5},
        }
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic, f)

        # Create other files
        for file_name, data in [
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("weather.json", {"temp": 20}),
            ("gear.json", [{"customMakeModel": "Cached Shoes"}]),
            ("hr_zones.json", [{"zoneNumber": 1}]),
            ("vo2_max.json", {}),
            ("lactate_threshold.json", {}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Mock get_activity_details to return NEW data
        new_activity_details = {"activityId": activity_id, "maxchart": 3000}

        with patch(
            "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client"
        ) as mock_client_fn:
            mock_client_fn.return_value.get_activity_details.return_value = (
                new_activity_details
            )

            # Execute with force_refetch
            result = worker.collect_data(
                activity_id, force_refetch=["activity_details"]
            )

            # Verify API was called ONLY for activity_details
            mock_client_fn.return_value.get_activity_details.assert_called_once()

            # Verify result contains NEW activity_details
            assert result["activity"]["maxchart"] == 3000

            # Verify other files were loaded from cache (NOT refetched)
            assert result["gear"][0]["customMakeModel"] == "Cached Shoes"

    @pytest.mark.unit
    def test_collect_data_force_refetch_multiple_files(self, worker, tmp_path):
        """Test force_refetch=['weather', 'vo2_max'] refetches multiple files."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create full cache with OLD weather and vo2_max
        old_weather = {"temp": 15, "windSpeed": 5}
        old_vo2_max = {"vo2MaxValue": 45}

        with open(activity_dir / "weather.json", "w", encoding="utf-8") as f:
            json.dump(old_weather, f)
        with open(activity_dir / "vo2_max.json", "w", encoding="utf-8") as f:
            json.dump(old_vo2_max, f)

        # Create required files
        activity_basic = {
            "activityId": activity_id,
            "summaryDTO": {
                "duration": 3000,
                "startTimeLocal": "2025-10-10T06:00:00.0",
            },
        }
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic, f)

        for file_name, data in [
            ("activity_details.json", {"activityId": activity_id}),
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("gear.json", []),
            ("hr_zones.json", []),
            ("lactate_threshold.json", {}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Mock APIs to return NEW data
        new_weather = {"temp": 20, "windSpeed": 10}
        new_vo2_max = {"generic": {"vo2MaxValue": 50}}

        with patch(
            "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client"
        ) as mock_client_fn:
            mock_client_fn.return_value.get_activity_weather.return_value = new_weather
            mock_client_fn.return_value.get_max_metrics.return_value = new_vo2_max

            # Execute with force_refetch for multiple files
            result = worker.collect_data(
                activity_id, force_refetch=["weather", "vo2_max"]
            )

            # Verify APIs were called ONLY for weather and vo2_max
            mock_client_fn.return_value.get_activity_weather.assert_called_once()
            mock_client_fn.return_value.get_max_metrics.assert_called_once()

            # Verify results contain NEW data
            assert result["weather"]["temp"] == 20
            assert result["weather"]["windSpeed"] == 10

            # Verify vo2_max.json file was updated (refetched from API)
            # Note: VO2 max processing may transform the data
            vo2_max_file = activity_dir / "vo2_max.json"
            assert vo2_max_file.exists()

    @pytest.mark.unit
    def test_collect_data_default_behavior(self, worker, tmp_path):
        """Test force_refetch=None uses cache-first (no API calls)."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create full cache
        activity_basic = {
            "activityId": activity_id,
            "summaryDTO": {"trainingEffect": 3.5},
        }
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic, f)

        for file_name, data in [
            ("activity_details.json", {"activityId": activity_id}),
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("weather.json", {"temp": 20}),
            ("gear.json", [{"customMakeModel": "Cached Shoes"}]),
            ("hr_zones.json", []),
            ("vo2_max.json", {}),
            ("lactate_threshold.json", {}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        with patch(
            "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client"
        ) as mock_client_fn:
            # Execute with default force_refetch=None
            result = worker.collect_data(activity_id)

            # Verify NO API calls were made
            mock_client_fn.return_value.get_activity_details.assert_not_called()
            mock_client_fn.return_value.get_activity_weather.assert_not_called()
            mock_client_fn.return_value.get_max_metrics.assert_not_called()

            # Verify cache was used
            assert result["gear"][0]["customMakeModel"] == "Cached Shoes"
