"""
Tests for Lactate Threshold Inserter

Test coverage:
- Unit tests for insert_lactate_threshold function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.lactate_threshold import insert_lactate_threshold


class TestLactateThresholdInserter:
    """Test suite for Lactate Threshold Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with lactate_threshold."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 22.0,
            },
            "lactate_threshold": {
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
            },
        }

        performance_file = tmp_path / "20615445009.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_lactate_threshold_success(self, sample_performance_file, tmp_path):
        """Test insert_lactate_threshold inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_lactate_threshold(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_lactate_threshold_missing_file(self, tmp_path):
        """Test insert_lactate_threshold handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_lactate_threshold(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_lactate_threshold_no_data(self, tmp_path):
        """Test insert_lactate_threshold handles missing lactate_threshold."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_lactate_threshold(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_lactate_threshold_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_lactate_threshold actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_lactate_threshold(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

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
        assert abs(row[2] - 0.314) < 0.001  # speed_mps
        assert row[4] == 345  # functional_threshold_power
        assert abs(row[5] - 5.0) < 0.1  # power_to_weight
        assert abs(row[6] - 69.0) < 0.1  # weight

        conn.close()
