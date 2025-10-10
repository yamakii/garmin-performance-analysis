"""Integration tests for RawDataExtractor with real data files."""

import json


class TestRawDataExtractorIntegration:
    """Test RawDataExtractor with real old/new format files."""

    def test_extract_from_old_format_file(self, fixture_base_path):
        """Test extraction from old format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # Old format: activity.json in 20594901208
        old_file = fixture_base_path / "data/raw/activity/20594901208/activity.json"
        assert old_file.exists(), "Fixture data should be available"

        with open(old_file) as f:
            activity_data = json.load(f)

        extractor = RawDataExtractor()

        # Test training effect extraction
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_new_format_file(self, fixture_base_path):
        """Test extraction from new format activity file."""
        from tools.ingest.garmin_worker import RawDataExtractor

        # New format: activity.json in 20615445009
        activity_file = (
            fixture_base_path / "data/raw/activity/20615445009/activity.json"
        )
        assert activity_file.exists(), "Fixture data should be available"

        with open(activity_file) as f:
            activity_data = json.load(f)

        extractor = RawDataExtractor()

        # Test training effect extraction from activity
        te = extractor.extract_training_effect(activity_data)
        assert "aerobicTrainingEffect" in te or "anaerobicTrainingEffect" in te
        # New format has float values like 3.5999999046325684
        assert te["aerobicTrainingEffect"] > 0

    def test_extract_from_raw_data_structure(self, fixture_base_path):
        """Test extraction from wrapped raw_data structure."""
        from tools.ingest.garmin_worker import RawDataExtractor

        old_file = fixture_base_path / "data/raw/activity/20594901208/activity.json"
        assert old_file.exists(), "Fixture data should be available"

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
