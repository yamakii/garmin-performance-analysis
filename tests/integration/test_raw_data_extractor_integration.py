"""Integration tests for RawDataExtractor with real data files."""

import json
from pathlib import Path

import pytest


@pytest.mark.integration
class TestRawDataExtractorIntegration:
    """Test RawDataExtractor with real old/new format files."""

    def test_extract_from_old_format_file(self):
        """Test extraction from real old format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # Old format: activity.json in 20594901208
        old_file = Path("data/raw/activity/20594901208/activity.json")
        assert old_file.exists(), "Old format test file not found"

        with open(old_file) as f:
            activity_data = json.load(f)

        extractor = RawDataExtractor()

        # Test format detection
        format_type = extractor.detect_format(activity_data)
        assert format_type == "old", f"Expected 'old', got '{format_type}'"

        # Test training effect extraction
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_new_format_file(self):
        """Test extraction from real new format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # New format needs both activity.json and activity_details.json
        activity_file = Path("data/raw/activity/20615445009/activity.json")
        details_file = Path("data/raw/activity/20615445009/activity_details.json")
        assert activity_file.exists(), "New format activity file not found"
        assert details_file.exists(), "New format details file not found"

        with open(activity_file) as f:
            activity_data = json.load(f)
        with open(details_file) as f:
            details_data = json.load(f)

        # Simulate raw_data structure with activity_details
        raw_data = {"activity": activity_data, "activity_details": details_data}

        extractor = RawDataExtractor()

        # Test format detection (needs activity_details to detect new format)
        format_type = extractor.detect_format(raw_data)
        assert format_type == "new", f"Expected 'new', got '{format_type}'"

        # Test training effect extraction from activity
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        # New format has float values like 3.5999999046325684
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_raw_data_structure(self):
        """Test extraction from wrapped raw_data structure."""
        from tools.ingest.garmin_worker import RawDataExtractor

        old_file = Path("data/raw/activity/20594901208/activity.json")
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
