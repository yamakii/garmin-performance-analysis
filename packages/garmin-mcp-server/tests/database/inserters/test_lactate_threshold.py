"""
Tests for Lactate Threshold Inserter

Test coverage:
- Unit tests for insert_lactate_threshold function
- Integration tests with DuckDB
"""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.lactate_threshold import insert_lactate_threshold


class TestLactateThresholdInserter:
    """Test suite for Lactate Threshold Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample lactate_threshold.json file (raw API response)."""
        # Raw API format has speed_and_heart_rate and power at top level
        lactate_threshold_data = {
            "speed_and_heart_rate": {
                "userProfilePK": 91627893,
                "version": 1757675098963,
                "calendarDate": "2025-09-12T20:04:58.947",
                "sequence": 1757675098963,
                "speed": 0.31388801000000005,
                "heartRate": 168,
            },
            "power": {
                "userProfilePk": 91627893,
                "calendarDate": "2025-10-07T22:05:01.0",
                "origin": "weight",
                "sport": "RUNNING",
                "functionalThresholdPower": 345,
                "powerToWeight": 5.0,
                "weight": 69.0,
            },
        }

        lt_file = tmp_path / "20615445009.json"
        with open(lt_file, "w", encoding="utf-8") as f:
            json.dump(lactate_threshold_data, f, ensure_ascii=False, indent=2)

        return lt_file

    @pytest.mark.unit
    def test_insert_lactate_threshold_success(
        self, sample_performance_file, initialized_db_path
    ):
        """Test insert_lactate_threshold inserts data successfully."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_lactate_threshold(
            raw_lactate_threshold_file=str(sample_performance_file),
            activity_id=20615445009,
            conn=conn,
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_lactate_threshold_missing_file(self, initialized_db_path):
        """Test insert_lactate_threshold handles missing file gracefully."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_lactate_threshold(
            raw_lactate_threshold_file="/nonexistent/file.json",
            activity_id=12345,
            conn=conn,
        )

        # Should return True (not an error, lactate threshold is optional)
        assert result is True

    @pytest.mark.unit
    def test_insert_lactate_threshold_no_data(self, tmp_path, initialized_db_path):
        """Test insert_lactate_threshold handles missing lactate_threshold data."""
        lt_data: dict = {}  # Empty file
        lt_file = tmp_path / "lactate_threshold.json"
        with open(lt_file, "w", encoding="utf-8") as f:
            json.dump(lt_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_lactate_threshold(
            raw_lactate_threshold_file=str(lt_file),
            activity_id=12345,
            conn=conn,
        )

        # Should return True (skips gracefully)
        assert result is True

    @pytest.mark.integration
    def test_insert_lactate_threshold_db_integration(
        self, sample_performance_file, initialized_db_path
    ):
        """Test insert_lactate_threshold actually writes to DuckDB."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_lactate_threshold(
            raw_lactate_threshold_file=str(sample_performance_file),
            activity_id=20615445009,
            conn=conn,
        )

        assert result is True

        # Check lactate_threshold table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "lactate_threshold" in table_names

        # Check lactate_threshold data
        lt_data = conn.execute(
            "SELECT * FROM lactate_threshold WHERE activity_id = 20615445009"
        ).fetchall()
        assert len(lt_data) == 1

        # Verify data values
        row = lt_data[0]
        assert row[0] == 20615445009  # activity_id
        assert row[1] == 168  # heart_rate
        assert abs(row[2] - 3.1389) < 0.001  # speed_mps (0.31388801 × 10 = 3.1389 m/s)
        assert row[4] == 345  # functional_threshold_power
        assert abs(row[5] - 5.0) < 0.1  # power_to_weight
        assert abs(row[6] - 69.0) < 0.1  # weight

        conn.close()
