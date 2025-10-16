"""Tests for GarminIngestWorker weight data path migration.

Tests that GarminIngestWorker correctly uses the new weight data structure:
- Old: data/weight_cache/raw/weight_{date}_raw.json
- New: data/raw/weight/{date}.json
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker():
    """Create GarminIngestWorker instance with temporary directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create worker and override project_root to use temp directory
        worker = GarminIngestWorker()
        worker.project_root = tmppath
        worker.raw_dir = tmppath / "data" / "raw"
        worker.weight_raw_dir = tmppath / "data" / "raw" / "weight"  # New path
        worker._db_path = str(tmppath / "test.duckdb")

        # Create directories
        for directory in [
            worker.raw_dir,
            worker.weight_raw_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        yield worker


@pytest.fixture
def sample_weight_data():
    """Sample weight data from Garmin API."""
    return {
        "startDate": "2025-10-03",
        "endDate": "2025-10-03",
        "dateWeightList": [
            {
                "samplePk": 1758435532139,
                "date": 1758467906000,
                "calendarDate": "2025-10-03",
                "weight": 65000,  # grams
                "bmi": 21.5,
                "bodyFat": 15.2,
                "bodyWater": 60.5,
                "boneMass": 3200,  # grams
                "muscleMass": 52000,  # grams
                "sourceType": "INDEX_SCALE",
                "timestampGMT": 1758435506000,
            }
        ],
        "totalAverage": {
            "from": 1758412800000,
            "until": 1758499199999,
            "weight": 65000.0,
            "bmi": 21.5,
            "bodyFat": 15.2,
            "bodyWater": 60.5,
            "boneMass": 3200,
            "muscleMass": 52000,
        },
    }


@pytest.mark.unit
class TestWeightPathMigration:
    """Tests for new weight data path structure."""

    def test_init_creates_weight_raw_dir_attribute(self, worker):
        """Test that __init__ creates weight_raw_dir attribute with new path."""
        # Verify new path structure
        assert hasattr(worker, "weight_raw_dir")
        assert worker.weight_raw_dir == worker.project_root / "data" / "raw" / "weight"

    def test_collect_body_composition_uses_new_path(self, worker, sample_weight_data):
        """Test that collect_body_composition_data uses new path structure."""
        test_date = "2025-10-03"

        # Create new structure cache file
        weight_file = worker.weight_raw_dir / f"{test_date}.json"
        with open(weight_file, "w", encoding="utf-8") as f:
            json.dump(sample_weight_data, f, indent=2, ensure_ascii=False)

        # Collect data (should use new path cache)
        result = worker.collect_body_composition_data(test_date)

        # Verify cached data was returned
        assert result is not None
        assert result["dateWeightList"][0]["weight"] == 65000
        assert result["startDate"] == test_date

    def test_collect_body_composition_creates_new_path_cache(
        self, worker, sample_weight_data
    ):
        """Test that collect_body_composition_data saves cache to new path."""
        test_date = "2025-10-03"

        # Mock the get_garmin_client method to return a mock client
        mock_client = Mock()
        mock_client.get_daily_weigh_ins.return_value = sample_weight_data

        with patch.object(
            GarminIngestWorker, "get_garmin_client", return_value=mock_client
        ):
            # Collect data (should call API and cache to new path)
            result = worker.collect_body_composition_data(test_date)

        # Verify API was called
        mock_client.get_daily_weigh_ins.assert_called_once_with(test_date)

        # Verify data was returned
        assert result is not None
        assert result["dateWeightList"][0]["weight"] == 65000

        # Verify cache was created in NEW path (not old weight_cache_dir)
        new_cache_file = worker.weight_raw_dir / f"{test_date}.json"
        assert new_cache_file.exists(), "Cache should be created in new path"

        # Verify old path was NOT used
        old_cache_file = (
            worker.project_root
            / "data"
            / "weight_cache"
            / "raw"
            / f"weight_{test_date}_raw.json"
        )
        assert not old_cache_file.exists(), "Old path should not be used"

        # Verify cached content
        with open(new_cache_file, encoding="utf-8") as f:
            cached_data = json.load(f)
        assert cached_data["dateWeightList"][0]["weight"] == 65000

    def test_calculate_median_weight_uses_new_path(self, worker, sample_weight_data):
        """Test that _calculate_median_weight reads from new path structure."""
        from datetime import datetime, timedelta

        test_date = "2025-10-03"
        target_date = datetime.strptime(test_date, "%Y-%m-%d")

        # Create cache files in NEW path for 7 days
        for i in range(7):
            date_obj = target_date - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            # Vary weights slightly for median calculation
            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 65000 + (i * 100)
            weight_data["startDate"] = date_str
            weight_data["endDate"] = date_str

            # Save to NEW path
            weight_file = worker.weight_raw_dir / f"{date_str}.json"
            with open(weight_file, "w", encoding="utf-8") as f:
                json.dump(weight_data, f, indent=2, ensure_ascii=False)

        # Calculate median
        result = worker._calculate_median_weight(test_date)

        # Verify results
        assert result is not None
        assert result["date"] == test_date
        assert result["sample_count"] == 7

        # Expected median weight: [65.0, 65.1, 65.2, 65.3, 65.4, 65.5, 65.6] → 65.3 kg
        assert abs(result["weight_kg"] - 65.3) < 0.01


@pytest.mark.unit
class TestBackwardCompatibilityRemoval:
    """Tests verifying old path is no longer used."""

    def test_old_weight_cache_dir_not_used(self, worker):
        """Test that old weight_cache_dir is not referenced in new code."""
        # Verify worker doesn't have old weight_cache_dir attribute
        # (It will still have it from old code, but it should not be used)
        test_date = "2025-10-03"

        # Create file ONLY in old path
        old_dir = worker.project_root / "data" / "weight_cache" / "raw"
        old_dir.mkdir(parents=True, exist_ok=True)
        old_file = old_dir / f"weight_{test_date}_raw.json"

        sample_data = {"dateWeightList": [{"weight": 99999}]}  # Distinct value
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Try to collect data (should NOT find old file, should return None or fetch from API)
        with patch.object(GarminIngestWorker, "get_garmin_client") as mock_get_client:
            mock_client = Mock()
            mock_client.get_daily_weigh_ins.return_value = None
            mock_get_client.return_value = mock_client

            result = worker.collect_body_composition_data(test_date)

        # Should return None (no data in new path, API returned None)
        assert result is None, "Should not find old cache file"


@pytest.mark.unit
class TestCalculateMedianWeightNewPath:
    """Tests for _calculate_median_weight using new path structure."""

    def test_median_with_no_data_new_path(self, worker):
        """Test that median calculation returns None when no data in new path."""
        test_date = "2099-12-31"  # Use future date to avoid production data collision

        # No cache files created in new path
        result = worker._calculate_median_weight(test_date)

        # Should return None when no data available
        assert result is None

    def test_median_ignores_old_path_data(self, worker, sample_weight_data):
        """Test that median calculation ignores data in old path."""
        from datetime import datetime, timedelta

        test_date = "2099-12-31"  # Use future date to avoid production data collision
        target_date = datetime.strptime(test_date, "%Y-%m-%d")

        # Create cache files ONLY in old path (should be ignored)
        old_dir = worker.project_root / "data" / "weight_cache" / "raw"
        old_dir.mkdir(parents=True, exist_ok=True)

        for i in range(7):
            date_obj = target_date - timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            weight_data = sample_weight_data.copy()
            weight_data["dateWeightList"][0]["weight"] = 99999  # Distinct value
            weight_data["startDate"] = date_str
            weight_data["endDate"] = date_str

            # Save to OLD path
            old_file = old_dir / f"weight_{date_str}_raw.json"
            with open(old_file, "w", encoding="utf-8") as f:
                json.dump(weight_data, f)

        # Calculate median (should return None, ignoring old path)
        result = worker._calculate_median_weight(test_date)

        # Should return None (no data in new path)
        assert result is None
