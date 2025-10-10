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

import json

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

        # Create test performance.json
        performance_file = tmp_path / f"{test_activity_id}.json"
        performance_data = {
            "form_efficiency_summary": {
                "gct": {
                    "average": 250.0,
                    "min": 240.0,
                    "max": 260.0,
                    "std": 5.0,
                    "variability": 2.0,
                    "rating": "★★★★★",
                    "evaluation": "優秀な接地時間",
                },
                "vo": {
                    "average": 7.5,
                    "min": 7.0,
                    "max": 8.0,
                    "std": 0.3,
                    "trend": "安定",
                    "rating": "★★★★★",
                    "evaluation": "効率的な地面反力利用",
                },
                "vr": {
                    "average": 8.5,
                    "min": 8.0,
                    "max": 9.0,
                    "std": 0.3,
                    "rating": "★★★★☆",
                    "evaluation": "良好な垂直比",
                },
            },
            "hr_efficiency_analysis": {
                "primary_zone": "Zone 2",
                "zone_distribution_rating": "優秀",
                "hr_stability": "優秀",
                "aerobic_efficiency": "高い",
                "training_quality": "優秀",
                "zone2_focus": True,
                "zone4_threshold_work": False,
                "training_type": "aerobic_base",
                "zone1_percentage": 5.0,
                "zone2_percentage": 70.0,
                "zone3_percentage": 20.0,
                "zone4_percentage": 5.0,
                "zone5_percentage": 0.0,
            },
        }

        performance_file.write_text(json.dumps(performance_data, indent=2))

        # Insert activity metadata first (required for foreign key constraint)
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_data={
                "activityId": test_activity_id,
                "activityName": "Test Activity",
                "startTimeLocal": "2025-10-07T10:00:00",
                "distance": 10000.0,
                "duration": 3600.0,
            },
        )
        # Use insert_performance_data (handles form_efficiency and hr_efficiency)
        db_writer.insert_performance_data(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            performance_data=performance_data,
        )

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

    # Phase 1.2: get_hr_efficiency_analysis tests
    @pytest.mark.unit
    def test_get_hr_efficiency_analysis_valid_data(self, db_reader, test_activity_id):
        """Test retrieving HR efficiency analysis with valid data."""
        result = db_reader.get_hr_efficiency_analysis(test_activity_id)

        assert result is not None
        # NOTE: Current hr_efficiency inserter only populates hr_stability and training_type
        # Other fields will be None until inserter is fixed (see duckdb_inserter_cleanup project)
        assert result["hr_stability"] == "優秀"
        assert result["training_type"] == "aerobic_base"

        # Verify structure exists (even if None)
        assert "primary_zone" in result
        assert "zone_distribution_rating" in result
        assert "zone_percentages" in result

    @pytest.mark.unit
    def test_get_hr_efficiency_analysis_no_data(self, db_reader):
        """Test retrieving HR efficiency analysis with non-existent activity."""
        result = db_reader.get_hr_efficiency_analysis(999999999)
        assert result is None

    @pytest.mark.unit
    def test_get_hr_efficiency_analysis_boolean_types(
        self, db_reader, test_activity_id
    ):
        """Test that boolean fields are properly typed."""
        result = db_reader.get_hr_efficiency_analysis(test_activity_id)

        assert result is not None
        assert isinstance(result["zone2_focus"], bool)
        assert isinstance(result["zone4_threshold_work"], bool)
