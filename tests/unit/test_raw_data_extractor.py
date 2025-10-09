"""Unit tests for RawDataExtractor class."""


class TestRawDataExtractor:
    """Test RawDataExtractor for old/new format compatibility."""

    def test_detect_format_old(self):
        """Test detection of old format (has summaryDTO)."""
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "activityId": 20594901208,
            "summaryDTO": {
                "trainingEffect": 3.5,
            },
        }

        extractor = RawDataExtractor()
        assert extractor.detect_format(raw_data) == "old"

    def test_detect_format_new(self):
        """Test detection of new format (has metricDescriptors)."""
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "activityId": 20615445009,
            "metricDescriptors": [],
            "summaryDTO": {
                "trainingEffect": 3.5,
            },
        }

        extractor = RawDataExtractor()
        assert extractor.detect_format(raw_data) == "new"

    def test_detect_format_unknown(self):
        """Test detection of unknown format."""
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "activityId": 12345,
        }

        extractor = RawDataExtractor()
        assert extractor.detect_format(raw_data) == "unknown"

    def test_extract_training_effect_old_toplevel(self):
        """Test extraction from old format with top-level training_effect key."""
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "activityId": 20594901208,
            "training_effect": {
                "aerobicTrainingEffect": 3.5,
                "anaerobicTrainingEffect": 1.2,
            },
            "summaryDTO": {
                "trainingEffect": 3.0,  # Should prioritize top-level
            },
        }

        extractor = RawDataExtractor()
        result = extractor.extract_training_effect(raw_data)

        assert result == {
            "aerobicTrainingEffect": 3.5,
            "anaerobicTrainingEffect": 1.2,
        }

    def test_extract_training_effect_old_summary(self):
        """Test extraction from old format summaryDTO."""
        from tools.ingest.garmin_worker import RawDataExtractor

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
        from tools.ingest.garmin_worker import RawDataExtractor

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
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "activityId": 12345,
        }

        extractor = RawDataExtractor()
        result = extractor.extract_training_effect(raw_data)

        assert result == {}

    def test_extract_from_raw_data(self):
        """Test full extraction from raw_data dict."""
        from tools.ingest.garmin_worker import RawDataExtractor

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

    def test_extract_from_raw_data_with_toplevel_key(self):
        """Test extraction prioritizing top-level training_effect key."""
        from tools.ingest.garmin_worker import RawDataExtractor

        raw_data = {
            "training_effect": {
                "aerobicTrainingEffect": 4.0,
                "anaerobicTrainingEffect": 2.0,
            },
            "activity": {
                "summaryDTO": {
                    "trainingEffect": 3.5,
                },
            },
        }

        extractor = RawDataExtractor()
        result = extractor.extract_from_raw_data(raw_data)

        assert result["training_effect"] == {
            "aerobicTrainingEffect": 4.0,
            "anaerobicTrainingEffect": 2.0,
        }
