"""
Tests for HR Efficiency Inserter

Test coverage:
- Unit tests for insert_hr_efficiency function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.hr_efficiency import insert_hr_efficiency


class TestHREfficiencyInserter:
    """Test suite for HR Efficiency Inserter."""

    @pytest.fixture
    def sample_raw_files(self, tmp_path):
        """Create sample hr_zones.json and activity.json files."""
        # Create hr_zones.json
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 490.546},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 1041.858},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 507.274},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 675.8},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        # Create activity.json
        activity_data = {
            "summaryDTO": {
                "averageHR": 148.0,
                "maxHR": 175.0,
                "minHR": 120.0,
                "trainingEffectLabel": "THRESHOLD_WORK",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        return hr_zones_file, activity_file

    @pytest.mark.unit
    def test_insert_hr_efficiency_success(self, sample_raw_files, tmp_path):
        """Test insert_hr_efficiency inserts data successfully."""
        hr_zones_file, activity_file = sample_raw_files
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=20615445009,
            db_path=str(db_path),
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_hr_efficiency_missing_file(self, tmp_path):
        """Test insert_hr_efficiency handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_hr_efficiency_no_required_files(self, tmp_path):
        """Test insert_hr_efficiency handles missing required files."""
        db_path = tmp_path / "test.duckdb"

        # Missing both files
        result = insert_hr_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_hr_zones_file=None,
            raw_activity_file=None,
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_hr_efficiency_db_integration(self, sample_raw_files, tmp_path):
        """Test insert_hr_efficiency actually writes to DuckDB."""
        import duckdb

        hr_zones_file, activity_file = sample_raw_files
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=20615445009,
            db_path=str(db_path),
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check hr_efficiency table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "hr_efficiency" in table_names

        # Check hr_efficiency data
        hr_eff = conn.execute(
            "SELECT * FROM hr_efficiency WHERE activity_id = 20615445009"
        ).fetchall()
        assert len(hr_eff) == 1

        # Verify data values
        row = hr_eff[0]
        assert row[0] == 20615445009  # activity_id
        assert row[8] == "threshold_work"  # training_type
        assert row[3] is not None  # hr_stability

        conn.close()

    @pytest.fixture
    def sample_hr_zones_file(self, tmp_path):
        """Create sample hr_zones.json file."""
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 88.001, "zoneLowBoundary": 116},
            {"zoneNumber": 2, "secsInZone": 576.894, "zoneLowBoundary": 130},
            {"zoneNumber": 3, "secsInZone": 1488.727, "zoneLowBoundary": 145},
            {"zoneNumber": 4, "secsInZone": 0.0, "zoneLowBoundary": 159},
            {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 174},
        ]

        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones, f, ensure_ascii=False, indent=2)

        return hr_zones_file

    @pytest.fixture
    def sample_activity_file(self, tmp_path):
        """Create sample activity.json file."""
        activity_data = {
            "activityId": 20636804823,
            "summaryDTO": {
                "averageHR": 143.0,
                "maxHR": 156.0,
                "minHR": 70.0,
                "trainingEffectLabel": "AEROBIC_BASE",
            },
        }

        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        return activity_file

    @pytest.mark.unit
    def test_insert_hr_efficiency_raw_data_success(
        self, sample_hr_zones_file, sample_activity_file, tmp_path
    ):
        """Test insert_hr_efficiency with raw data mode."""
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_hr_zones_file=str(sample_hr_zones_file),
            raw_activity_file=str(sample_activity_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_hr_efficiency_raw_data_db_integration(
        self, sample_hr_zones_file, sample_activity_file, tmp_path
    ):
        """Test insert_hr_efficiency with raw data actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_hr_zones_file=str(sample_hr_zones_file),
            raw_activity_file=str(sample_activity_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check hr_efficiency table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "hr_efficiency" in table_names

        # Check hr_efficiency data
        hr_eff = conn.execute(
            "SELECT * FROM hr_efficiency WHERE activity_id = 20636804823"
        ).fetchall()
        assert len(hr_eff) == 1

        # Verify data values
        row = hr_eff[0]
        assert row[0] == 20636804823  # activity_id
        assert row[8] == "aerobic_base"  # training_type (from trainingEffectLabel)
        assert row[3] is not None  # hr_stability

        # Verify zone percentages
        total_time = 88.001 + 576.894 + 1488.727
        expected_zone1_pct = round((88.001 / total_time) * 100, 2)
        expected_zone2_pct = round((576.894 / total_time) * 100, 2)
        expected_zone3_pct = round((1488.727 / total_time) * 100, 2)

        assert row[9] == expected_zone1_pct  # zone1_percentage
        assert row[10] == expected_zone2_pct  # zone2_percentage
        assert row[11] == expected_zone3_pct  # zone3_percentage
        assert row[12] == 0.0  # zone4_percentage
        assert row[13] == 0.0  # zone5_percentage

        conn.close()

    @pytest.mark.unit
    def test_insert_hr_efficiency_raw_data_missing_files(self, tmp_path):
        """Test insert_hr_efficiency raw mode handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )

        assert result is False
