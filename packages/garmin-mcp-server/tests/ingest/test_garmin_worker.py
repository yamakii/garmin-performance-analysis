"""
Tests for GarminIngestWorker

Test coverage:
- Unit tests for data collection
- Unit tests for parquet creation
- Unit tests for metrics calculation
- Unit tests for data saving
"""

import json
from typing import Any
from unittest.mock import patch

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


class TestGarminIngestWorker:
    """Test suite for GarminIngestWorker."""

    @pytest.fixture
    def worker(self, tmp_path):
        """Create GarminIngestWorker instance with isolated tmp database."""
        worker = GarminIngestWorker()
        # Use tmp_path for isolated database to avoid interference
        worker._db_path = tmp_path / "test_garmin.duckdb"
        return worker

    @pytest.fixture
    def sample_raw_data(self):
        """Sample raw data matching actual Garmin API response structure."""
        return {
            "activity": {
                "activityId": 20464005432,
                "activityName": "Morning Run",
                "startTimeLocal": "2025-09-22 06:30:00",
                "distance": 5000,
                "duration": 1500,
                "averageHR": 145,
            },
            "splits": {
                "activityId": 20464005432,
                "lapDTOs": [
                    {
                        "startTimeGMT": "2025-09-22T06:30:00.0",
                        "distance": 1000,
                        "duration": 300.0,
                        "averageSpeed": 3.33,
                        "averageHR": 140,
                        "averageRunCadence": 170,
                        "averagePower": 250,
                        "groundContactTime": 240,
                        "verticalOscillation": 7.5,
                        "verticalRatio": 8.5,
                        "elevationGain": 10,
                        "elevationLoss": 5,
                        "maxElevation": 50,
                        "minElevation": 40,
                    },
                    {
                        "startTimeGMT": "2025-09-22T06:35:00.0",
                        "distance": 1000,
                        "duration": 295.0,
                        "averageSpeed": 3.39,
                        "averageHR": 145,
                        "averageRunCadence": 172,
                        "averagePower": 255,
                        "groundContactTime": 238,
                        "verticalOscillation": 7.3,
                        "verticalRatio": 8.3,
                        "elevationGain": 15,
                        "elevationLoss": 8,
                        "maxElevation": 55,
                        "minElevation": 42,
                    },
                ],
                "eventDTOs": [],
            },
            "weather": {
                "temp": 18,
                "apparentTemp": 16,
                "windSpeed": 5,
                "relativeHumidity": 65,
                "weatherTypeDTO": {"weatherTypePk": 1},
            },
            "gear": [
                {
                    "gearPk": 12345,
                    "customMakeModel": "Nike Pegasus",
                    "gearTypeName": "Shoes",
                    "gearStatusName": "active",
                }
            ],
            "hr_zones": [
                {"zoneNumber": 1, "secsInZone": 300.0, "zoneLowBoundary": 100},
                {"zoneNumber": 2, "secsInZone": 600.0, "zoneLowBoundary": 120},
                {"zoneNumber": 3, "secsInZone": 400.0, "zoneLowBoundary": 140},
                {"zoneNumber": 4, "secsInZone": 200.0, "zoneLowBoundary": 160},
                {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 180},
            ],
        }

    @pytest.mark.unit
    def test_get_activity_date_from_db(self, tmp_path):
        """Test get_activity_date retrieves date from DuckDB."""
        import duckdb

        # Setup: Create temporary DuckDB with activity
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (12345, '2025-09-22')"
        )
        conn.close()

        # Execute
        worker = GarminIngestWorker(db_path=str(db_path))
        result = worker.get_activity_date(12345)

        # Verify
        assert result == "2025-09-22"

    @pytest.mark.unit
    def test_get_activity_date_not_found(self, tmp_path):
        """Test get_activity_date returns None for missing activity."""
        import duckdb

        # Setup: Create empty DuckDB
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.close()

        # Execute
        worker = GarminIngestWorker(db_path=str(db_path))
        result = worker.get_activity_date(99999)

        # Verify
        assert result is None

    @pytest.mark.unit
    def test_collect_data_uses_cache_when_available(self, worker, tmp_path):
        """Test collect_data prioritizes cache over API calls."""
        # Setup: Create cached file
        worker.raw_dir = tmp_path
        cached_file = tmp_path / "12345_raw.json"
        cached_data = {
            "activity": {"activityId": 12345},
            "splits": {"activityId": 12345, "lapDTOs": [], "eventDTOs": []},
            "weather": {"temp": 20},
            "gear": [{"customMakeModel": "Cached Shoes"}],
            "hr_zones": [{"zoneNumber": 1, "zoneLowBoundary": 100}],
        }
        with open(cached_file, "w", encoding="utf-8") as f:
            json.dump(cached_data, f)

        # Execute
        result = worker.collect_data(12345)

        # Verify cache was used (not API)
        assert result["gear"][0]["customMakeModel"] == "Cached Shoes"
        assert "activity" in result
        assert "splits" in result
        assert "weather" in result
        assert "gear" in result
        assert "hr_zones" in result

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

    @pytest.mark.integration
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

    @pytest.mark.integration
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

    # =============================================
    # New tests for get_activity() API integration
    # =============================================

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

    @pytest.mark.integration
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

    # =============================================
    # Tests for force_refetch functionality
    # =============================================

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

            # The key test: API was called to refetch (not loaded from old cache)
            # Old cache had {"vo2MaxValue": 45}, API called means refetch succeeded

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

    @pytest.mark.integration
    def test_force_refetch_with_duckdb_cache(self, worker, tmp_path):
        """Test DuckDB cache bypasses force_refetch (DuckDB has priority)."""
        activity_id = 12345
        date = "2025-10-10"

        # Mock _check_duckdb_cache to return complete performance data
        complete_performance_data = {
            "basic_metrics": {"distance_km": 5.0},
            "heart_rate_zones": {},
            "efficiency_metrics": {},
            "training_effect": {},
            "power_to_weight": {},
            "split_metrics": [],
            "vo2_max": {},
            "lactate_threshold": {},
            "form_efficiency_summary": {},
            "hr_efficiency_analysis": {},
            "performance_trends": {},
        }

        with patch.object(worker, "_check_duckdb_cache") as mock_duckdb_check:
            mock_duckdb_check.return_value = complete_performance_data

            with patch.object(worker, "collect_data") as mock_collect:
                # Execute with force_refetch
                result = worker.process_activity(
                    activity_id, date, force_refetch=["weather"]
                )

                # Verify collect_data was NOT called (DuckDB cache hit)
                mock_collect.assert_not_called()

                # Verify DuckDB cache was used
                assert result["source"] == "duckdb_cache"
