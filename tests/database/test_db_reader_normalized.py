"""
Tests for GarminDBReader normalized table access methods.

Test coverage:
- get_form_efficiency_summary: Retrieve form efficiency data from form_efficiency table
- get_hr_efficiency_analysis: Retrieve HR efficiency data from hr_efficiency table
- get_heart_rate_zones_detail: Retrieve heart rate zones from heart_rate_zones table
- get_vo2_max_data: Retrieve VO2 max data from vo2_max table
- get_lactate_threshold_data: Retrieve lactate threshold data from lactate_threshold table
- get_splits_all: Retrieve all split data (22 fields) from splits table
"""

import pytest

from tools.database.db_reader import GarminDBReader
from tools.database.db_writer import GarminDBWriter


class TestGarminDBReaderNormalized:
    """Test suite for GarminDBReader normalized table access."""

    @pytest.fixture
    def test_activity_id(self):
        """Test activity ID."""
        return 20615445009

    @pytest.fixture
    def db_reader(self, tmp_path, test_activity_id):
        """Create GarminDBReader with test database containing normalized data."""
        db_path = tmp_path / "test.duckdb"

        # Create db_writer and insert activity metadata first
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_type="running",
        )

        # Create test performance data matching inserter's expected format
        # NOTE: inserter expects gct_stats, vo_stats, vr_stats (not gct, vo, vr)
        # NOTE: inserter currently only inserts stats and ratings, not evaluations/trend
        performance_data = {
            "form_efficiency_summary": {
                "gct_stats": {
                    "average": 250.0,
                    "min": 240.0,
                    "max": 260.0,
                    "std": 5.0,
                },
                "gct_rating": "★★★★★",
                "vo_stats": {
                    "average": 7.5,
                    "min": 7.0,
                    "max": 8.0,
                    "std": 0.3,
                },
                "vo_rating": "★★★★★",
                "vr_stats": {
                    "average": 8.5,
                    "min": 8.0,
                    "max": 9.0,
                    "std": 0.3,
                },
                "vr_rating": "★★★★☆",
            },
        }

        # Insert performance data into DuckDB
        db_writer.insert_performance_data(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            performance_data=performance_data,
        )

        # Return reader instance
        return GarminDBReader(db_path=str(db_path))

    # Phase 1.1: get_form_efficiency_summary tests
    @pytest.mark.unit
    def test_get_form_efficiency_summary_valid_data(self, db_reader, test_activity_id):
        """Test retrieving form efficiency summary with valid data."""
        result = db_reader.get_form_efficiency_summary(test_activity_id)

        assert result is not None
        assert "gct" in result
        assert "vo" in result
        assert "vr" in result

        # Verify GCT data (only fields inserted by current inserter)
        assert result["gct"]["average"] == 250.0
        assert result["gct"]["min"] == 240.0
        assert result["gct"]["max"] == 260.0
        assert result["gct"]["std"] == 5.0
        assert result["gct"]["variability"] == pytest.approx(
            2.0, rel=0.01
        )  # Calculated: 5/250 * 100
        assert result["gct"]["rating"] == "★★★★★"

        # Verify VO data
        assert result["vo"]["average"] == 7.5
        assert result["vo"]["min"] == 7.0
        assert result["vo"]["max"] == 8.0
        assert result["vo"]["std"] == 0.3
        assert result["vo"]["rating"] == "★★★★★"

        # Verify VR data
        assert result["vr"]["average"] == 8.5
        assert result["vr"]["min"] == 8.0
        assert result["vr"]["max"] == 9.0
        assert result["vr"]["std"] == 0.3
        assert result["vr"]["rating"] == "★★★★☆"

    @pytest.mark.unit
    def test_get_form_efficiency_summary_no_data(self, db_reader):
        """Test retrieving form efficiency summary with non-existent activity."""
        result = db_reader.get_form_efficiency_summary(999999999)
        assert result is None

    @pytest.mark.unit
    def test_get_form_efficiency_summary_data_structure(
        self, db_reader, test_activity_id
    ):
        """Test that form efficiency summary has correct structure."""
        result = db_reader.get_form_efficiency_summary(test_activity_id)

        assert result is not None

        # Verify top-level keys
        required_keys = ["gct", "vo", "vr"]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        # Verify GCT structure (all fields should be present even if None)
        gct_keys = [
            "average",
            "min",
            "max",
            "std",
            "variability",
            "rating",
            "evaluation",
        ]
        for key in gct_keys:
            assert key in result["gct"], f"Missing GCT key: {key}"

        # Verify VO structure
        vo_keys = ["average", "min", "max", "std", "trend", "rating", "evaluation"]
        for key in vo_keys:
            assert key in result["vo"], f"Missing VO key: {key}"

        # Verify VR structure
        vr_keys = ["average", "min", "max", "std", "rating", "evaluation"]
        for key in vr_keys:
            assert key in result["vr"], f"Missing VR key: {key}"
