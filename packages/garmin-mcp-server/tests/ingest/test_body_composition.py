"""Tests for body composition data processing in GarminIngestWorker."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def test_date():
    """
    Fixed future date for test isolation.

    Using 2099-06-15 ensures no conflict with production data.
    """
    return "2099-06-15"


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance with temporary directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create worker and override project_root to use temp directory
        worker = GarminIngestWorker()
        worker.project_root = tmppath
        worker.raw_dir = tmppath / "data" / "raw"
        worker.weight_raw_dir = tmppath / "data" / "raw" / "weight"  # NEW
        worker._db_path = str(tmppath / "test.duckdb")

        # Create directories
        for directory in [
            worker.raw_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        yield worker


@pytest.fixture
def sample_weight_data():
    """Sample weight data from Garmin API."""
    return {
        "dateWeightList": [
            {
                "calendarDate": "2025-10-03",
                "weight": 65000,  # grams
                "bmi": 21.5,
                "bodyFat": 15.2,
                "bodyWater": 60.5,
                "boneMass": 3200,  # grams
                "muscleMass": 52000,  # grams
                "physiqueRating": 5,
                "visceralFat": 3,
                "metabolicAge": 25,
                "sourceType": "INDEX_SCALE",
            }
        ]
    }


def create_weight_cache_file(cache_dir: Path, date: str, weight_data: dict):
    """Create a cached weight data file in NEW path structure."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{date}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(weight_data, f, indent=2, ensure_ascii=False)


@pytest.mark.unit
class TestCalculateMedianWeight:
    """Tests for _calculate_median_weight method."""

    def test_median_with_7_days_data(self, worker, sample_weight_data, test_date):
        """Test median calculation with complete 7 days of data."""
        target_date = test_date

        # Create cache files for 7 days
        for i in range(7):
            date_obj = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            # Vary weights slightly for median calculation
            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (
                i * 100
            )  # 65.0, 65.1, 65.2, ...
            weight_data["dateWeightList"][0]["bmi"] = 21.5 + (i * 0.1)
            weight_data["dateWeightList"][0]["bodyFat"] = 15.0 + (i * 0.2)

            create_weight_cache_file(worker.weight_raw_dir, date_str, weight_data)

        # Calculate median
        result = worker._calculate_median_weight(target_date)

        # Verify results
        assert result is not None
        assert result["date"] == target_date
        assert result["source"] == "7DAY_MEDIAN"
        assert result["sample_count"] == 7

        # Expected median weight: [65.0, 65.1, 65.2, 65.3, 65.4, 65.5, 65.6] → 65.3 kg
        assert abs(result["weight_kg"] - 65.3) < 0.01

        # Expected median BMI: [21.5, 21.6, 21.7, 21.8, 21.9, 22.0, 22.1] → 21.8
        assert abs(result["bmi"] - 21.8) < 0.01

        # Expected median body fat: [15.0, 15.2, 15.4, 15.6, 15.8, 16.0, 16.2] → 15.6
        assert abs(result["body_fat_percentage"] - 15.6) < 0.01

    @pytest.mark.slow
    def test_median_with_partial_data(self, worker, sample_weight_data, test_date):
        """Test median calculation with only 3 days of data."""
        target_date = test_date

        # Create cache files for only 3 days
        for i in range(3):
            date_obj = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (
                i * 200
            )  # 65.0, 65.2, 65.4

            create_weight_cache_file(worker.weight_raw_dir, date_str, weight_data)

        # Calculate median
        result = worker._calculate_median_weight(target_date)

        # Verify results
        assert result is not None
        assert result["sample_count"] == 3

        # Expected median weight: [65.0, 65.2, 65.4] → 65.2 kg
        assert abs(result["weight_kg"] - 65.2) < 0.01

    def test_median_with_missing_days(self, worker, sample_weight_data, test_date):
        """Test median calculation when some days have no data."""
        target_date = test_date

        # Create cache files for days 0, 2, 4, 6 only (skip 1, 3, 5)
        for i in [0, 2, 4, 6]:
            date_obj = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (i * 100)

            create_weight_cache_file(worker.weight_raw_dir, date_str, weight_data)

        # Calculate median
        result = worker._calculate_median_weight(target_date)

        # Verify results
        assert result is not None
        assert result["sample_count"] >= 4  # At least 4 days have data

        # Expected median weight: [65.0, 65.2, 65.4, 65.6] → 65.3 kg
        assert abs(result["weight_kg"] - 65.3) < 0.01

    def test_median_with_no_data(self, worker, test_date):
        """Test median calculation when no data is available."""
        target_date = test_date

        # No cache files created
        result = worker._calculate_median_weight(target_date)

        # Should return None when no data available
        assert result is None

    def test_unit_conversion_grams_to_kg(self, worker, sample_weight_data, test_date):
        """Test that weight values are correctly converted from grams to kg."""
        target_date = test_date

        # Create cache file with known gram values
        weight_data = sample_weight_data.copy()
        weight_data["dateWeightList"][0]["weight"] = 65432  # 65.432 kg
        weight_data["dateWeightList"][0]["muscleMass"] = 52100  # 52.1 kg
        weight_data["dateWeightList"][0]["boneMass"] = 3250  # 3.25 kg

        create_weight_cache_file(worker.weight_raw_dir, target_date, weight_data)

        # Calculate median
        result = worker._calculate_median_weight(target_date)

        # Verify conversion
        assert result is not None
        assert abs(result["weight_kg"] - 65.432) < 0.001
        assert abs(result["muscle_mass_kg"] - 52.1) < 0.001
        assert abs(result["bone_mass_kg"] - 3.25) < 0.001


@pytest.mark.unit
class TestProcessBodyComposition:
    """Tests for process_body_composition method."""

    def test_process_saves_direct_measurement(
        self, worker, sample_weight_data, test_date
    ):
        """Test that process_body_composition saves direct measurements only."""
        target_date = test_date

        # Create raw cache file with direct measurement
        create_weight_cache_file(worker.weight_raw_dir, target_date, sample_weight_data)

        # Mock db_writer to avoid actual database operations
        with patch("garmin_mcp.database.db_writer.GarminDBWriter") as mock_writer_class:
            mock_writer = Mock()
            mock_writer.insert_body_composition.return_value = True
            mock_writer_class.return_value = mock_writer

            # Process body composition
            result = worker.process_body_composition(target_date)

        # Verify results
        assert result["status"] == "success"
        assert result["date"] == target_date
        assert "direct measurement" in result["message"]
        assert abs(result["weight_kg"] - 65.0) < 0.01  # 65000g → 65.0kg

        # Verify db_writer was called with raw data (not median)
        mock_writer.insert_body_composition.assert_called_once()
        call_args = mock_writer.insert_body_composition.call_args
        assert call_args[1]["date"] == target_date
        assert call_args[1]["weight_data"] == sample_weight_data

    def test_process_handles_no_data(self, worker, test_date):
        """Test error handling when no data is available."""
        target_date = test_date

        # No cache files created

        # Process body composition
        result = worker.process_body_composition(target_date)

        # Verify error status
        assert result["status"] == "no_data"
        assert result["date"] == target_date
        assert "No body composition data" in result["message"]


@pytest.mark.unit
class TestCollectBodyCompositionData:
    """Tests for collect_body_composition_data method."""

    def test_collect_uses_cache_when_available(
        self, worker, sample_weight_data, test_date
    ):
        """Test that cached data is used when available."""
        target_date = test_date

        # Create cache file
        create_weight_cache_file(worker.weight_raw_dir, target_date, sample_weight_data)

        # Collect data (should use cache, not API)
        result = worker.collect_body_composition_data(target_date)

        # Verify cached data was returned
        assert result is not None
        assert result["dateWeightList"][0]["weight"] == 65000

    def test_collect_fetches_from_api_when_no_cache(
        self, worker, sample_weight_data, test_date
    ):
        """Test that API is called when cache doesn't exist."""
        target_date = test_date

        # Mock the get_garmin_client method to return a mock client
        mock_client = Mock()
        mock_client.get_daily_weigh_ins.return_value = sample_weight_data

        with patch.object(
            GarminIngestWorker, "get_garmin_client", return_value=mock_client
        ):
            # Collect data (should call API)
            result = worker.collect_body_composition_data(target_date)

        # Verify API was called
        mock_client.get_daily_weigh_ins.assert_called_once_with(target_date)

        # Verify data was returned
        assert result is not None
        assert result["dateWeightList"][0]["weight"] == 65000

        # Verify cache was created
        cache_file = worker.weight_raw_dir / f"{target_date}.json"  # NEW naming
        assert cache_file.exists()

        # Verify cached content
        with open(cache_file, encoding="utf-8") as f:
            cached_data = json.load(f)
        assert cached_data["dateWeightList"][0]["weight"] == 65000


@pytest.mark.unit
class TestBackwardCompatibility:
    """Tests for backward compatibility with existing data."""

    def test_process_existing_raw_data_new_structure(
        self, worker, sample_weight_data, test_date
    ):
        """
        Test that weight data in new structure can be processed.

        Uses fixture data to ensure the new logic works without
        requiring real production data.
        """
        target_date = test_date

        # Create weight data files for 7 days (for median calculation)
        from datetime import datetime, timedelta

        for i in range(7):
            date_obj = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            # Vary weights slightly for median calculation
            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (i * 100)
            weight_data["dateWeightList"][0]["calendarDate"] = date_str

            create_weight_cache_file(worker.weight_raw_dir, date_str, weight_data)

        # Calculate median using new logic
        median_data = worker._calculate_median_weight(target_date)

        # Verify median calculation succeeded
        assert (
            median_data is not None
        ), "Median calculation should succeed with fixture data"
        assert "weight_kg" in median_data
        assert median_data["sample_count"] == 7

        # Verify data structure
        expected_fields = [
            "date",
            "weight_kg",
            "bmi",
            "body_fat_percentage",
            "muscle_mass_kg",
            "bone_mass_kg",
            "hydration_percentage",
            "source",
            "sample_count",
        ]
        for field in expected_fields:
            assert field in median_data, f"Expected field '{field}' in median_data"

        # Verify weight is reasonable (between 40kg and 150kg for humans)
        assert (
            40 <= median_data["weight_kg"] <= 150
        ), f"Weight {median_data['weight_kg']}kg is unreasonable"

    @pytest.mark.slow
    def test_median_calculation_with_new_structure(
        self, worker, sample_weight_data, test_date
    ):
        """
        Test that median calculation works with new file structure.

        Verifies that the median calculation produces consistent results
        with the new path structure using fixture data.
        """
        target_date = test_date

        # Create weight data files for median calculation
        from datetime import datetime, timedelta

        for i in range(5):
            date_obj = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (i * 50)
            weight_data["dateWeightList"][0]["calendarDate"] = date_str

            create_weight_cache_file(worker.weight_raw_dir, date_str, weight_data)

        # Calculate median
        median_data = worker._calculate_median_weight(target_date)
        assert median_data is not None

        # Verify median data structure
        assert median_data["date"] == target_date
        assert median_data["source"] == "7DAY_MEDIAN"
        assert median_data["sample_count"] == 5
        assert median_data["weight_kg"] > 0
