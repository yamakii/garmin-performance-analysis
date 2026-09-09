"""GarminIngestWorker.load_from_cache(): activity.json, skip files, missing required file."""

import json

import pytest


class TestLoadFromCache:
    @pytest.mark.unit
    def test_load_from_cache_with_activity_json(self, worker, tmp_path):
        """Test load_from_cache with activity.json (new format) present."""
        # Setup: Create activity directory with activity.json
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create activity.json (basic info with summaryDTO)
        activity_basic_data = {
            "activityId": activity_id,
            "activityName": "Morning Run",
            "summaryDTO": {
                "trainingEffect": 3.5,
                "anaerobicTrainingEffect": 2.0,
                "aerobicTrainingEffectMessage": "Improving",
                "anaerobicTrainingEffectMessage": "Maintaining",
                "trainingEffectLabel": "Improving",
            },
        }
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic_data, f)

        # Create activity_details.json (chart data)
        activity_details_data = {"activityId": activity_id, "metricDescriptors": []}
        with open(activity_dir / "activity_details.json", "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f)

        # Create other required files
        for file_name, data in [
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("weather.json", {"temp": 20}),
            ("gear.json", [{"customMakeModel": "Test Shoes"}]),
            ("hr_zones.json", [{"zoneNumber": 1, "zoneLowBoundary": 100}]),
            ("vo2_max.json", {"generic": {"vo2MaxValue": 50}}),
            ("lactate_threshold.json", {"lactateThresholdBPM": 160}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute
        result = worker.load_from_cache(activity_id)

        # Verify
        assert result is not None
        assert "activity_basic" in result
        assert "activity" in result
        assert result["activity_basic"]["summaryDTO"]["trainingEffect"] == 3.5
        assert "training_effect" in result
        assert result["training_effect"]["aerobicTrainingEffect"] == 3.5

    @pytest.mark.unit
    def test_load_from_cache_with_skip_files(self, worker, tmp_path):
        """Test load_from_cache with skip_files allows partial cache."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create partial cache (missing activity_details.json intentionally)
        activity_basic = {"activityId": activity_id, "summaryDTO": {}}
        with open(activity_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_basic, f)

        # DO NOT create activity_details.json

        # Create other required files
        for file_name, data in [
            (
                "splits.json",
                {"activityId": activity_id, "lapDTOs": [], "eventDTOs": []},
            ),
            ("weather.json", {"temp": 20}),
            ("gear.json", []),
            ("hr_zones.json", []),
            ("vo2_max.json", {}),
            ("lactate_threshold.json", {}),
        ]:
            with open(activity_dir / file_name, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute with skip_files={'activity_details'}
        result = worker.load_from_cache(activity_id, skip_files={"activity_details"})

        # Verify partial data returned (no activity_details key)
        assert result is not None
        assert "activity_basic" in result
        assert "activity" not in result  # activity_details was skipped
        assert "splits" in result
        assert "weather" in result

    @pytest.mark.unit
    def test_load_from_cache_missing_required_file(self, worker, tmp_path):
        """Test load_from_cache returns None if required file is missing (not in skip_files)."""
        activity_id = 12345
        activity_dir = tmp_path / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        worker.raw_dir = tmp_path

        # Create partial cache (missing activity.json - REQUIRED file)
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

        # Execute with skip_files=set() (no files skipped)
        result = worker.load_from_cache(activity_id, skip_files=set())

        # Verify None returned (required activity.json missing)
        assert result is None
