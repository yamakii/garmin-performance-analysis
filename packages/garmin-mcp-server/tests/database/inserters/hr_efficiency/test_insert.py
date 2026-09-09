"""insert_hr_efficiency(): success, missing files, DB integration, raw-data path."""

import duckdb
import pytest

from garmin_mcp.database.inserters.hr_efficiency import (
    insert_hr_efficiency,
)


class TestInsertHREfficiency:
    @pytest.mark.unit
    def test_insert_hr_efficiency_success(self, sample_raw_files, initialized_db_path):
        """Test insert_hr_efficiency inserts data successfully."""
        hr_zones_file, activity_file = sample_raw_files
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20615445009,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_hr_efficiency_missing_file(self, tmp_path):
        """Test insert_hr_efficiency handles missing files."""
        conn = duckdb.connect(":memory:")

        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )
        conn.close()

        assert result is False

    @pytest.mark.unit
    def test_insert_hr_efficiency_no_required_files(self, tmp_path):
        """Test insert_hr_efficiency handles missing required files."""
        conn = duckdb.connect(":memory:")

        # Missing both files
        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file=None,
            raw_activity_file=None,
        )
        conn.close()

        assert result is False

    @pytest.mark.integration
    def test_insert_hr_efficiency_db_integration(
        self, sample_raw_files, initialized_db_path
    ):
        """Test insert_hr_efficiency actually writes to DuckDB."""

        hr_zones_file, activity_file = sample_raw_files
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20615445009,
            conn=conn,
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

    @pytest.mark.unit
    def test_insert_hr_efficiency_raw_data_success(
        self, sample_hr_zones_file, sample_activity_file, initialized_db_path
    ):
        """Test insert_hr_efficiency with raw data mode."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20636804823,
            conn=conn,
            raw_hr_zones_file=str(sample_hr_zones_file),
            raw_activity_file=str(sample_activity_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_hr_efficiency_raw_data_db_integration(
        self, sample_hr_zones_file, sample_activity_file, initialized_db_path
    ):
        """Test insert_hr_efficiency with raw data actually writes to DuckDB."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20636804823,
            conn=conn,
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
    def test_insert_hr_efficiency_raw_data_missing_files(self, initialized_db_path):
        """Test insert_hr_efficiency raw mode handles missing files."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )

        assert result is False
