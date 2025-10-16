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

        # Create test splits.json for form_efficiency
        splits_file = tmp_path / "splits.json"
        splits_data = {
            "activityId": test_activity_id,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "groundContactTime": 250.0,
                    "verticalOscillation": 7.5,
                    "verticalRatio": 8.5,
                },
                {
                    "lapIndex": 2,
                    "distance": 1000.0,
                    "groundContactTime": 240.0,
                    "verticalOscillation": 7.0,
                    "verticalRatio": 8.0,
                },
                {
                    "lapIndex": 3,
                    "distance": 1000.0,
                    "groundContactTime": 260.0,
                    "verticalOscillation": 8.0,
                    "verticalRatio": 9.0,
                },
            ],
        }
        splits_file.write_text(json.dumps(splits_data, indent=2))

        # Create raw data files for hr_efficiency
        hr_zones_file = tmp_path / "hr_zones.json"
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 180.0},  # 5%
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 2520.0},  # 70%
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 720.0},  # 20%
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 180.0},  # 5%
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},  # 0%
        ]
        hr_zones_file.write_text(json.dumps(hr_zones_data, indent=2))

        activity_file = tmp_path / "activity.json"
        activity_data = {
            "summaryDTO": {
                "averageHR": 140,  # Zone 2 range
                "maxHR": 155,  # Range: 155-128=27, 27/140=0.19 < 0.3 (優秀)
                "minHR": 128,
                "trainingEffectLabel": "AEROBIC_BASE",
            }
        }
        activity_file.write_text(json.dumps(activity_data, indent=2))

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
        # Use individual inserters directly
        from tools.database.inserters.form_efficiency import insert_form_efficiency
        from tools.database.inserters.hr_efficiency import insert_hr_efficiency

        insert_form_efficiency(
            activity_id=test_activity_id,
            db_path=str(db_path),
            raw_splits_file=str(splits_file),
        )
        insert_hr_efficiency(
            activity_id=test_activity_id,
            db_path=str(db_path),
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
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

        # Verify GCT data (calculated from [250, 240, 260])
        assert result["gct"]["average"] == 250.0
        assert result["gct"]["min"] == 240.0
        assert result["gct"]["max"] == 260.0
        assert result["gct"]["std"] == pytest.approx(
            10.0, rel=0.01
        )  # std([250,240,260])
        assert result["gct"]["variability"] == pytest.approx(
            4.0, rel=0.01
        )  # Calculated: 10/250 * 100
        assert result["gct"]["rating"] == "★★★★★"

        # Verify VO data (calculated from [7.5, 7.0, 8.0])
        assert result["vo"]["average"] == 7.5
        assert result["vo"]["min"] == 7.0
        assert result["vo"]["max"] == 8.0
        assert result["vo"]["std"] == pytest.approx(0.5, rel=0.01)  # std([7.5,7.0,8.0])
        assert result["vo"]["rating"] == "★★★★★"

        # Verify VR data (calculated from [8.5, 8.0, 9.0])
        assert result["vr"]["average"] == 8.5
        assert result["vr"]["min"] == 8.0
        assert result["vr"]["max"] == 9.0
        assert result["vr"]["std"] == pytest.approx(0.5, rel=0.01)  # std([8.5,8.0,9.0])
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


class TestGetHeartRateZonesDetail:
    """Test get_heart_rate_zones_detail method."""

    @pytest.fixture
    def db_reader_with_hr_zones(self, tmp_path, test_activity_id):
        """Create GarminDBReader with test database containing HR zones data."""
        db_path = tmp_path / "test.duckdb"

        # Create test hr_zones.json with raw data
        hr_zones_file = tmp_path / "hr_zones.json"
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 0, "secsInZone": 300.0},
            {"zoneNumber": 2, "zoneLowBoundary": 130, "secsInZone": 2520.0},
            {"zoneNumber": 3, "zoneLowBoundary": 150, "secsInZone": 720.0},
            {"zoneNumber": 4, "zoneLowBoundary": 165, "secsInZone": 180.0},
            {"zoneNumber": 5, "zoneLowBoundary": 180, "secsInZone": 0.0},
        ]
        hr_zones_file.write_text(json.dumps(hr_zones_data, indent=2))

        # Insert activity metadata and heart_rate_zones
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_data={
                "activityId": test_activity_id,
                "activityName": "Test Activity with HR Zones",
                "startTimeLocal": "2025-10-07T10:00:00",
                "distance": 10000.0,
                "duration": 3720.0,
            },
        )
        # Use heart_rate_zones inserter directly
        from tools.database.inserters.heart_rate_zones import insert_heart_rate_zones

        insert_heart_rate_zones(
            activity_id=test_activity_id,
            db_path=str(db_path),
            raw_hr_zones_file=str(hr_zones_file),
        )

        return GarminDBReader(db_path=str(db_path))

    @pytest.mark.unit
    def test_get_heart_rate_zones_detail_valid_data(
        self, db_reader_with_hr_zones, test_activity_id
    ):
        """Test successful retrieval of heart rate zones detail."""
        result = db_reader_with_hr_zones.get_heart_rate_zones_detail(test_activity_id)

        assert result is not None
        assert "zones" in result
        assert isinstance(result["zones"], list)

        # Verify 5 zones
        assert len(result["zones"]) == 5

        # Verify zone structure and data
        zone1 = result["zones"][0]
        assert zone1["zone_number"] == 1
        assert zone1["low_boundary"] == 0
        assert zone1["high_boundary"] == 129  # next_zone_low - 1 (130 - 1)
        assert zone1["time_in_zone_seconds"] == 300.0
        assert zone1["zone_percentage"] == pytest.approx(
            8.06, abs=0.1
        )  # 300/3720 * 100

        zone2 = result["zones"][1]
        assert zone2["zone_number"] == 2
        assert zone2["low_boundary"] == 130
        assert zone2["high_boundary"] == 149  # next_zone_low - 1 (150 - 1)
        assert zone2["time_in_zone_seconds"] == 2520.0
        assert zone2["zone_percentage"] == pytest.approx(
            67.74, abs=0.1
        )  # 2520/3720 * 100

    @pytest.mark.unit
    def test_get_heart_rate_zones_detail_no_data(self, db_reader_with_hr_zones):
        """Test retrieval with non-existent activity ID."""
        result = db_reader_with_hr_zones.get_heart_rate_zones_detail(999999999)
        assert result is None

    @pytest.mark.unit
    def test_get_heart_rate_zones_detail_sort_order(
        self, db_reader_with_hr_zones, test_activity_id
    ):
        """Test that zones are sorted by zone_number."""
        result = db_reader_with_hr_zones.get_heart_rate_zones_detail(test_activity_id)

        assert result is not None
        zones = result["zones"]

        # Verify ascending order
        for i in range(len(zones) - 1):
            assert zones[i]["zone_number"] < zones[i + 1]["zone_number"]

    @pytest.fixture
    def test_activity_id(self):
        """Test activity ID."""
        return 20615445009


class TestGetVO2MaxData:
    """Test get_vo2_max_data method."""

    @pytest.fixture
    def test_activity_id(self):
        """Test activity ID."""
        return 20615445009

    @pytest.fixture
    def db_reader_with_vo2max(self, tmp_path, test_activity_id):
        """Create GarminDBReader with test database containing VO2 max data."""
        db_path = tmp_path / "test.duckdb"

        # Create test vo2_max.json with raw data
        vo2_max_file = tmp_path / "vo2_max.json"
        vo2_max_data = {
            "generic": {
                "vo2MaxValue": 52,
                "vo2MaxPreciseValue": 52.3,
                "calendarDate": "2025-10-07",
                "fitnessAge": 25,
            }
        }
        vo2_max_file.write_text(json.dumps(vo2_max_data, indent=2))

        # Insert activity metadata and vo2_max
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_data={
                "activityId": test_activity_id,
                "activityName": "Test Activity with VO2 Max",
                "startTimeLocal": "2025-10-07T10:00:00",
                "distance": 10000.0,
                "duration": 3600.0,
            },
        )
        # Use vo2_max inserter directly
        from tools.database.inserters.vo2_max import insert_vo2_max

        insert_vo2_max(
            activity_id=test_activity_id,
            db_path=str(db_path),
            raw_vo2_max_file=str(vo2_max_file),
        )

        return GarminDBReader(db_path=str(db_path))

    @pytest.mark.unit
    def test_get_vo2_max_data_valid_data(self, db_reader_with_vo2max, test_activity_id):
        """Test retrieving VO2 max data with valid data."""
        result = db_reader_with_vo2max.get_vo2_max_data(test_activity_id)

        assert result is not None
        assert result["precise_value"] == 52.3
        assert result["value"] == 52.0
        assert result["date"] == "2025-10-07"
        assert result["fitness_age"] == 25
        assert result["category"] == 0  # Default (not in raw data)

    @pytest.mark.unit
    def test_get_vo2_max_data_no_data(self, db_reader_with_vo2max):
        """Test retrieving VO2 max data with non-existent activity."""
        result = db_reader_with_vo2max.get_vo2_max_data(999999999)
        assert result is None

    @pytest.mark.unit
    def test_get_vo2_max_data_structure(self, db_reader_with_vo2max, test_activity_id):
        """Test that VO2 max data has correct structure."""
        result = db_reader_with_vo2max.get_vo2_max_data(test_activity_id)

        assert result is not None
        required_keys = [
            "precise_value",
            "value",
            "date",
            "fitness_age",
            "category",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"


class TestGetLactateThresholdData:
    """Test get_lactate_threshold_data method."""

    @pytest.fixture
    def test_activity_id(self):
        """Test activity ID."""
        return 20615445009

    @pytest.fixture
    def db_reader_with_lactate(self, tmp_path, test_activity_id):
        """Create GarminDBReader with test database containing lactate threshold data."""
        db_path = tmp_path / "test.duckdb"

        # Create test lactate_threshold.json with raw data
        lactate_threshold_file = tmp_path / "lactate_threshold.json"
        lactate_threshold_data = {
            "speed_and_heart_rate": {
                "heartRate": 165,
                "speed": 3.5,
                "calendarDate": "2025-10-07T10:30:00.000",
            },
            "power": {
                "functionalThresholdPower": 250,
                "powerToWeight": 3.5,
                "weight": 71.4,
                "calendarDate": "2025-10-07T10:30:00.000",
            },
        }
        lactate_threshold_file.write_text(json.dumps(lactate_threshold_data, indent=2))

        # Insert activity metadata and lactate_threshold
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_data={
                "activityId": test_activity_id,
                "activityName": "Test Activity with Lactate Threshold",
                "startTimeLocal": "2025-10-07T10:00:00",
                "distance": 10000.0,
                "duration": 3600.0,
            },
        )
        # Use lactate_threshold inserter directly
        from tools.database.inserters.lactate_threshold import insert_lactate_threshold

        insert_lactate_threshold(
            activity_id=test_activity_id,
            db_path=str(db_path),
            raw_lactate_threshold_file=str(lactate_threshold_file),
        )

        return GarminDBReader(db_path=str(db_path))

    @pytest.mark.unit
    def test_get_lactate_threshold_data_valid_data(
        self, db_reader_with_lactate, test_activity_id
    ):
        """Test retrieving lactate threshold data with valid data."""
        result = db_reader_with_lactate.get_lactate_threshold_data(test_activity_id)

        assert result is not None
        assert result["heart_rate"] == 165
        assert result["speed_mps"] == 3.5
        assert "2025-10-07" in result["date_hr"]  # TIMESTAMP converted to string
        assert result["functional_threshold_power"] == 250
        assert result["power_to_weight"] == 3.5
        assert result["weight"] == 71.4
        assert "2025-10-07" in result["date_power"]  # TIMESTAMP converted to string

    @pytest.mark.unit
    def test_get_lactate_threshold_data_no_data(self, db_reader_with_lactate):
        """Test retrieving lactate threshold data with non-existent activity."""
        result = db_reader_with_lactate.get_lactate_threshold_data(999999999)
        assert result is None

    @pytest.mark.unit
    def test_get_lactate_threshold_data_timestamp_conversion(
        self, db_reader_with_lactate, test_activity_id
    ):
        """Test that TIMESTAMP fields are converted to strings."""
        result = db_reader_with_lactate.get_lactate_threshold_data(test_activity_id)

        assert result is not None
        # Verify date_hr and date_power are strings
        assert isinstance(result["date_hr"], str)
        assert isinstance(result["date_power"], str)


class TestGetSplitsAll:
    """Test get_splits_all method."""

    @pytest.fixture
    def test_activity_id(self):
        """Test activity ID."""
        return 20615445009

    @pytest.fixture
    def db_reader_with_splits(self, tmp_path, test_activity_id):
        """Create GarminDBReader with test database containing splits data."""
        db_path = tmp_path / "test.duckdb"

        # Create test performance.json with split_metrics (only fields that inserter uses)
        performance_file = tmp_path / f"{test_activity_id}.json"
        performance_data = {
            "split_metrics": [
                {
                    "split_number": 1,
                    "distance_km": 1.0,
                    "role_phase": "warmup",
                    "avg_pace_seconds_per_km": 330.0,
                    "avg_heart_rate": 140,
                    "avg_cadence": 170.0,
                    "avg_power": 250.0,
                    "ground_contact_time_ms": 245.0,
                    "vertical_oscillation_cm": 7.5,
                    "vertical_ratio_percent": 8.2,
                    "elevation_gain_m": 10.0,
                    "elevation_loss_m": 5.0,
                    "terrain_type": "平坦",
                },
                {
                    "split_number": 2,
                    "distance_km": 1.0,
                    "role_phase": "main",
                    "avg_pace_seconds_per_km": 300.0,
                    "avg_heart_rate": 155,
                    "avg_cadence": 175.0,
                    "avg_power": 270.0,
                    "ground_contact_time_ms": 240.0,
                    "vertical_oscillation_cm": 7.2,
                    "vertical_ratio_percent": 8.0,
                    "elevation_gain_m": 15.0,
                    "elevation_loss_m": 8.0,
                    "terrain_type": "やや起伏",
                },
            ]
        }
        performance_file.write_text(json.dumps(performance_data, indent=2))

        # Insert activity metadata and splits
        db_writer = GarminDBWriter(db_path=str(db_path))
        db_writer.insert_activity(
            activity_id=test_activity_id,
            activity_date="2025-10-07",
            activity_data={
                "activityId": test_activity_id,
                "activityName": "Test Activity with Splits",
                "startTimeLocal": "2025-10-07T10:00:00",
                "distance": 2000.0,
                "duration": 630.0,
            },
        )
        # Use splits inserter directly
        from tools.database.inserters.splits import insert_splits

        insert_splits(
            activity_id=test_activity_id,
            db_path=str(db_path),
        )

        return GarminDBReader(db_path=str(db_path))

    @pytest.mark.unit
    def test_get_splits_all_valid_data(self, db_reader_with_splits, test_activity_id):
        """Test retrieving all split data with valid data."""
        result = db_reader_with_splits.get_splits_all(test_activity_id)

        assert result is not None
        assert "splits" in result
        assert isinstance(result["splits"], list)
        assert len(result["splits"]) == 2

        # Verify first split has core fields (15 fields currently inserted by inserter)
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["distance_km"] == 1.0
        assert split1["role_phase"] == "warmup"
        assert split1["pace_str"] == "5:30"
        assert split1["avg_pace_seconds_per_km"] == 330.0
        assert split1["avg_heart_rate"] == 140
        # hr_zone is not inserted by current inserter
        assert split1["cadence"] == 170.0
        # cadence_rating is not inserted by current inserter
        assert split1["power"] == 250.0
        # power_efficiency, stride_length not inserted by current inserter
        assert split1["ground_contact_time_ms"] == 245.0
        assert split1["vertical_oscillation_cm"] == 7.5
        assert split1["vertical_ratio_percent"] == 8.2
        assert split1["elevation_gain_m"] == 10.0
        assert split1["elevation_loss_m"] == 5.0
        assert split1["terrain_type"] == "平坦"
        # environmental_conditions, wind_impact, temp_impact, environmental_impact not inserted

    @pytest.mark.unit
    def test_get_splits_all_no_data(self, db_reader_with_splits):
        """Test retrieving splits with non-existent activity."""
        result = db_reader_with_splits.get_splits_all(999999999)
        assert result == {"splits": []}

    @pytest.mark.unit
    def test_get_splits_all_field_completeness(
        self, db_reader_with_splits, test_activity_id
    ):
        """Test that all 22 fields are present in each split."""
        result = db_reader_with_splits.get_splits_all(test_activity_id)

        assert result is not None
        required_fields = [
            "split_number",
            "distance_km",
            "role_phase",
            "pace_str",
            "avg_pace_seconds_per_km",
            "avg_heart_rate",
            "hr_zone",
            "cadence",
            "cadence_rating",
            "power",
            "power_efficiency",
            "stride_length",
            "ground_contact_time_ms",
            "vertical_oscillation_cm",
            "vertical_ratio_percent",
            "elevation_gain_m",
            "elevation_loss_m",
            "terrain_type",
            "environmental_conditions",
            "wind_impact",
            "temp_impact",
            "environmental_impact",
        ]

        for split in result["splits"]:
            for field in required_fields:
                assert field in split, f"Missing field: {field}"
