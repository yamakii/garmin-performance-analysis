"""
Tests for GarminIngestWorker

Test coverage:
- Unit tests for data collection
- Unit tests for parquet creation
- Unit tests for metrics calculation
- Unit tests for data saving
"""

import json
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
