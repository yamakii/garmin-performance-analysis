"""Unit tests for RawDataExtractor class."""

import pytest


@pytest.mark.unit
class TestRawDataExtractor:
    """Test RawDataExtractor for old/new format compatibility."""

    def test_extract_training_effect_old_summary(self):
        """Test extraction from old format summaryDTO."""
        from garmin_mcp.ingest.raw_data_fetcher import RawDataExtractor

        raw_data = {
            "activityId": 20594901208,
            "summaryDTO": {
                "trainingEffect": 3.5,
                "anaerobicTrainingEffect": 1.2,
            },
        }

        extractor = RawDataExtractor()
        result = extractor.extract_training_effect(raw_data)

        assert result == {
            "aerobicTrainingEffect": 3.5,
            "anaerobicTrainingEffect": 1.2,
        }

    def test_extract_training_effect_new(self):
        """Test extraction from new format (summaryDTO still exists)."""
        from garmin_mcp.ingest.raw_data_fetcher import RawDataExtractor

        raw_data = {
            "activityId": 20615445009,
            "metricDescriptors": [],
            "summaryDTO": {
                "trainingEffect": 3.5999999046325684,
                "anaerobicTrainingEffect": 1.2000000476837158,
            },
        }

        extractor = RawDataExtractor()
        result = extractor.extract_training_effect(raw_data)

        assert result == {
            "aerobicTrainingEffect": 3.5999999046325684,
            "anaerobicTrainingEffect": 1.2000000476837158,
        }

    def test_extract_training_effect_missing(self):
        """Test extraction when training effect data is missing."""
        from garmin_mcp.ingest.raw_data_fetcher import RawDataExtractor

        raw_data = {
            "activityId": 12345,
        }

        extractor = RawDataExtractor()
        result = extractor.extract_training_effect(raw_data)

        assert result == {}

    def test_extract_from_raw_data(self):
        """Test full extraction from raw_data dict."""
        from garmin_mcp.ingest.raw_data_fetcher import RawDataExtractor

        raw_data = {
            "activity": {
                "activityId": 20594901208,
                "summaryDTO": {
                    "trainingEffect": 3.5,
                    "anaerobicTrainingEffect": 1.2,
                },
            },
            "activity_details": {
                "someData": "value",
            },
        }

        extractor = RawDataExtractor()
        result = extractor.extract_from_raw_data(raw_data)

        assert "training_effect" in result
        assert result["training_effect"] == {
            "aerobicTrainingEffect": 3.5,
            "anaerobicTrainingEffect": 1.2,
        }
