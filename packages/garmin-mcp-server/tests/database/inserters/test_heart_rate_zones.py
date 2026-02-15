"""
Tests for Heart Rate Zones Inserter

Test coverage:
- Unit tests for insert_heart_rate_zones function
- Integration tests with DuckDB
"""

import json

import pytest

from garmin_mcp.database.inserters.heart_rate_zones import insert_heart_rate_zones


class TestHeartRateZonesInserter:
    """Test suite for Heart Rate Zones Inserter."""

    @pytest.fixture
    def sample_hr_zones_file(self, tmp_path):
        """Create sample hr_zones.json file."""
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

        return hr_zones_file

    @pytest.mark.unit
    def test_insert_heart_rate_zones_success(self, sample_hr_zones_file, tmp_path):
        """Test insert_heart_rate_zones inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            activity_id=20615445009,
            db_path=str(db_path),
            raw_hr_zones_file=str(sample_hr_zones_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_heart_rate_zones_missing_file(self, tmp_path):
        """Test insert_heart_rate_zones handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            activity_id=12345,
            db_path=str(db_path),
            raw_hr_zones_file="/nonexistent/file.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_heart_rate_zones_no_file_provided(self, tmp_path):
        """Test insert_heart_rate_zones handles missing hr_zones file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            activity_id=12345,
            db_path=str(db_path),
            raw_hr_zones_file=None,
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_heart_rate_zones_db_integration(
        self, sample_hr_zones_file, tmp_path
    ):
        """Test insert_heart_rate_zones actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            activity_id=20615445009,
            db_path=str(db_path),
            raw_hr_zones_file=str(sample_hr_zones_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check heart_rate_zones table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "heart_rate_zones" in table_names

        # Check heart_rate_zones data
        hr_zones = conn.execute(
            "SELECT * FROM heart_rate_zones WHERE activity_id = 20615445009 ORDER BY zone_number"
        ).fetchall()
        assert len(hr_zones) == 5

        # Verify zone 1 data
        zone1 = hr_zones[0]
        assert zone1[0] == 20615445009  # activity_id
        assert zone1[1] == 1  # zone_number
        assert zone1[2] == 117  # zone_low_boundary
        assert zone1[3] == 130  # zone_high_boundary
        assert abs(zone1[4] - 490.546) < 0.01  # time_in_zone_seconds
        assert abs(zone1[5] - 18.06) < 0.5  # zone_percentage (490.546/2715.478*100)

        # Verify zone 2 data
        zone2 = hr_zones[1]
        assert zone2[1] == 2  # zone_number
        assert zone2[2] == 131  # zone_low_boundary
        assert zone2[3] == 145  # zone_high_boundary
        assert abs(zone2[4] - 1041.858) < 0.01  # time_in_zone_seconds

        # Verify zone 5 data (edge case with 0 time)
        zone5 = hr_zones[4]
        assert zone5[1] == 5  # zone_number
        assert zone5[2] == 175  # zone_low_boundary
        assert zone5[3] == 220  # zone_high_boundary (max HR)
        assert zone5[4] == 0.0  # time_in_zone_seconds
        assert zone5[5] == 0.0  # zone_percentage

        conn.close()
