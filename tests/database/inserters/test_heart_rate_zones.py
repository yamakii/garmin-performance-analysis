"""
Tests for Heart Rate Zones Inserter

Test coverage:
- Unit tests for insert_heart_rate_zones function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.heart_rate_zones import insert_heart_rate_zones


class TestHeartRateZonesInserter:
    """Test suite for Heart Rate Zones Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with heart_rate_zones."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 2715.478,
            },
            "heart_rate_zones": {
                "zone1": {
                    "low": 117,
                    "secs_in_zone": 490.546,
                },
                "zone2": {
                    "low": 131,
                    "secs_in_zone": 1041.858,
                },
                "zone3": {
                    "low": 146,
                    "secs_in_zone": 507.274,
                },
                "zone4": {
                    "low": 160,
                    "secs_in_zone": 675.8,
                },
                "zone5": {
                    "low": 175,
                    "secs_in_zone": 0.0,
                },
            },
        }

        performance_file = tmp_path / "20615445009.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_heart_rate_zones_success(self, sample_performance_file, tmp_path):
        """Test insert_heart_rate_zones inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_heart_rate_zones_missing_file(self, tmp_path):
        """Test insert_heart_rate_zones handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_heart_rate_zones_no_data(self, tmp_path):
        """Test insert_heart_rate_zones handles missing heart_rate_zones."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_heart_rate_zones_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_heart_rate_zones actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_heart_rate_zones(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
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
