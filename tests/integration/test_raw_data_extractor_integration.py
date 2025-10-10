"""Integration tests for RawDataExtractor with real data files."""

import json
from pathlib import Path

import pytest


class TestRawDataExtractorIntegration:
    """Test RawDataExtractor with real old/new format files."""

    def test_extract_from_old_format_file(self):
        """Test extraction from real old format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # Old format: activity.json in 20594901208
        old_file = Path("data/raw/activity/20594901208/activity.json")
        if not old_file.exists():
            pytest.skip("Real activity data not available in fixtures")

        with open(old_file) as f:
            activity_data = json.load(f)

        extractor = RawDataExtractor()

        # Test training effect extraction
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_new_format_file(self):
        """Test extraction from real new format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # New format: activity.json in 20615445009
        activity_file = Path("data/raw/activity/20615445009/activity.json")
        if not activity_file.exists():
            pytest.skip("Real activity data not available in fixtures")

        with open(activity_file) as f:
            activity_data = json.load(f)

        extractor = RawDataExtractor()

        # Test training effect extraction from activity
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        # New format has float values like 3.5999999046325684
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_raw_data_structure(self):
        """Test extraction from wrapped raw_data structure."""
        from tools.ingest.garmin_worker import RawDataExtractor

        old_file = Path("data/raw/activity/20594901208/activity.json")
        if not old_file.exists():
            pytest.skip("Real activity data not available in fixtures")

        with open(old_file) as f:
            activity_data = json.load(f)

        # Simulate raw_data structure
        raw_data = {
            "activity": activity_data,
            "activity_details": {},
        }

        extractor = RawDataExtractor()
        result = extractor.extract_from_raw_data(raw_data)

        assert "training_effect" in result
        assert "aerobicTrainingEffect" in result["training_effect"]
