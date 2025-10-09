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

import pandas as pd
import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


class TestGarminIngestWorker:
    """Test suite for GarminIngestWorker."""

    @pytest.fixture
    def worker(self):
        """Create GarminIngestWorker instance."""
        return GarminIngestWorker()

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE NOT NULL
            )
        """
        )
        conn.execute(
            "INSERT INTO activities (activity_id, date) VALUES (12345, '2025-09-22')"
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE NOT NULL
            )
        """
        )
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
    def test_create_parquet_dataset(self, worker, sample_raw_data):
        """Test create_parquet_dataset creates DataFrame with correct columns."""
        df = worker.create_parquet_dataset(sample_raw_data)

        # Verify DataFrame structure
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2  # 2 splits

        # Verify required columns
        required_columns = [
            "split_number",
            "distance_km",
            "duration_seconds",
            "avg_pace_seconds_per_km",
            "avg_heart_rate",
            "avg_cadence",
            "avg_power",
            "ground_contact_time_ms",
            "vertical_oscillation_cm",
            "vertical_ratio_percent",
            "elevation_gain_m",
            "elevation_loss_m",
            "max_elevation_m",
            "min_elevation_m",
            "terrain_type",
        ]
        for col in required_columns:
            assert col in df.columns

    @pytest.mark.unit
    def test_calculate_split_metrics(self, worker, sample_raw_data):
        """Test _calculate_split_metrics generates performance.json structure."""
        df = worker.create_parquet_dataset(sample_raw_data)
        metrics = worker._calculate_split_metrics(df, sample_raw_data)

        # Verify 11 sections exist
        assert "basic_metrics" in metrics
        assert "heart_rate_zones" in metrics
        assert "split_metrics" in metrics
        assert "efficiency_metrics" in metrics
        assert "training_effect" in metrics
        assert "power_to_weight" in metrics
        assert "vo2_max" in metrics
        assert "lactate_threshold" in metrics
        assert "form_efficiency_summary" in metrics
        assert "hr_efficiency_analysis" in metrics
        assert "performance_trends" in metrics

    @pytest.mark.unit
    def test_save_data_creates_files(self, worker, sample_raw_data, tmp_path):
        """Test save_data creates all required files."""
        df = pd.DataFrame(
            {
                "split_number": [1, 2],
                "distance_km": [1.0, 1.0],
                "avg_pace_seconds_per_km": [300, 295],
            }
        )
        performance_data: dict[str, dict[str, int]] = {"basic_metrics": {}}

        with patch("tools.ingest.garmin_worker.Path") as mock_path:
            mock_path.return_value = tmp_path

            result = worker.save_data(
                20464005432, sample_raw_data, df, performance_data
            )

            # Verify result contains file paths
            assert "raw_file" in result
            assert "parquet_file" in result
            assert "performance_file" in result
            assert "precheck_file" in result

    @pytest.mark.unit
    def test_process_activity_full_pipeline(self, worker):
        """Test process_activity executes full pipeline."""
        with (
            patch.object(worker, "collect_data") as mock_collect,
            patch.object(worker, "create_parquet_dataset") as mock_parquet,
            patch.object(worker, "_calculate_split_metrics") as mock_calc,
            patch.object(worker, "save_data") as mock_save,
        ):
            # Setup mocks
            mock_collect.return_value = {
                "activity": {},
                "splits": {"lapDTOs": []},
            }
            mock_parquet.return_value = pd.DataFrame()
            mock_calc.return_value = {}
            mock_save.return_value = {
                "activity_id": 12345,
                "date": "2025-09-22",
            }

            result = worker.process_activity(12345, "2025-09-22")

            # Verify all steps were called
            mock_collect.assert_called_once_with(12345)
            mock_parquet.assert_called_once()
            mock_calc.assert_called_once()
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
        assert cache_file.exists(), "Test requires cached activity data"

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

        # Verify files were created
        files = result["files"]
        assert "raw_file" in files
        assert "parquet_file" in files
        assert "performance_file" in files
        assert "precheck_file" in files

        # Verify parquet file exists and is valid
        parquet_file = worker.parquet_dir / f"{activity_id}.parquet"
        assert parquet_file.exists()

        # Verify performance file exists and has all 11 sections
        performance_file = worker.performance_dir / f"{activity_id}.json"
        assert performance_file.exists()

        with open(performance_file, encoding="utf-8") as f:
            performance_data = json.load(f)

        assert "basic_metrics" in performance_data
        assert "heart_rate_zones" in performance_data
        assert "split_metrics" in performance_data
        assert "efficiency_metrics" in performance_data
        assert "training_effect" in performance_data
        assert "power_to_weight" in performance_data
        assert "vo2_max" in performance_data
        assert "lactate_threshold" in performance_data
        assert "form_efficiency_summary" in performance_data
        assert "hr_efficiency_analysis" in performance_data
        assert "performance_trends" in performance_data

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

        with patch.object(worker, "get_garmin_client") as mock_client:
            # Setup all API mocks
            mock_client.return_value.get_activity.return_value = mock_activity_basic
            mock_client.return_value.get_activity_details.return_value = (
                mock_activity_details
            )
            mock_client.return_value.get_activity_splits.return_value = mock_splits
            mock_client.return_value.get_activity_weather.return_value = mock_weather
            mock_client.return_value.get_activity_gear.return_value = mock_gear
            mock_client.return_value.get_activity_hr_in_timezones.return_value = (
                mock_hr_zones
            )
            mock_client.return_value.get_activity_vo2_max.return_value = mock_vo2_max
            mock_client.return_value.get_activity_lactate_threshold.return_value = (
                mock_lactate
            )
            mock_client.return_value.get_activity_evaluation.return_value = {}

            # Execute
            result = worker.collect_data(activity_id)

            # Verify get_activity() was called
            mock_client.return_value.get_activity.assert_called_once_with(
                str(activity_id)
            )

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
