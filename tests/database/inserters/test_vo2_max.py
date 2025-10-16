"""
Tests for VO2 Max Inserter

Test coverage:
- Unit tests for insert_vo2_max function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.vo2_max import insert_vo2_max


class TestVO2MaxInserter:
    """Test suite for VO2 Max Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with vo2_max."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 22.0,
            },
            "vo2_max": {
                "precise_value": 44.7,
                "value": 45.0,
                "date": "2025-08-19",
                "fitness_age": None,
                "category": 0,
            },
        }

        performance_file = tmp_path / "20107340187.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_vo2_max_success(self, sample_performance_file, tmp_path):
        """Test insert_vo2_max inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_vo2_max(
            performance_file=str(sample_performance_file),
            activity_id=20107340187,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_vo2_max_missing_file(self, tmp_path):
        """Test insert_vo2_max handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_vo2_max(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_vo2_max_no_data(self, tmp_path):
        """Test insert_vo2_max handles missing vo2_max."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_vo2_max(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_vo2_max_db_integration(self, sample_performance_file, tmp_path):
        """Test insert_vo2_max actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_vo2_max(
            performance_file=str(sample_performance_file),
            activity_id=20107340187,
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check vo2_max table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "vo2_max" in table_names

        # Check vo2_max data
        vo2_data = conn.execute(
            "SELECT * FROM vo2_max WHERE activity_id = 20107340187"
        ).fetchall()
        assert len(vo2_data) == 1

        # Verify data values
        row = vo2_data[0]
        assert row[0] == 20107340187  # activity_id
        assert abs(row[1] - 44.7) < 0.1  # precise_value
        assert abs(row[2] - 45.0) < 0.1  # value
        assert str(row[3]) == "2025-08-19"  # date
        assert row[4] is None  # fitness_age
        assert row[5] == 0  # category

        conn.close()

    @pytest.fixture
    def sample_raw_vo2_max_file(self, tmp_path):
        """Create sample vo2_max.json file (raw API response)."""
        raw_vo2_max = {
            "generic": {
                "vo2MaxValue": 45,
                "vo2MaxPreciseValue": 44.7,
                "calendarDate": "2025-08-19",
                "fitnessAge": None,
            }
        }

        raw_file = tmp_path / "vo2_max.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_vo2_max, f, ensure_ascii=False, indent=2)

        return raw_file

    @pytest.mark.unit
    def test_extract_vo2_max_from_raw_success(self, sample_raw_vo2_max_file):
        """Test _extract_vo2_max_from_raw extracts data correctly."""
        from tools.database.inserters.vo2_max import _extract_vo2_max_from_raw

        result = _extract_vo2_max_from_raw(str(sample_raw_vo2_max_file))

        assert result is not None
        assert result["precise_value"] == 44.7
        assert result["value"] == 45.0
        assert result["date"] == "2025-08-19"
        assert result["fitness_age"] is None
        assert result["category"] == 0

    @pytest.mark.unit
    def test_insert_vo2_max_from_raw_data(self, sample_raw_vo2_max_file, tmp_path):
        """Test insert_vo2_max with raw data (performance_file=None)."""
        db_path = tmp_path / "test.duckdb"

        result = insert_vo2_max(
            performance_file=None,
            activity_id=20107340187,
            db_path=str(db_path),
            raw_vo2_max_file=str(sample_raw_vo2_max_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_vo2_max_raw_data_integrity(self, sample_raw_vo2_max_file, tmp_path):
        """Test raw data mode produces same result as performance.json mode."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Insert from raw data
        result = insert_vo2_max(
            performance_file=None,
            activity_id=20107340187,
            db_path=str(db_path),
            raw_vo2_max_file=str(sample_raw_vo2_max_file),
        )

        assert result is True

        # Verify data in DuckDB matches expected values
        conn = duckdb.connect(str(db_path))
        vo2_data = conn.execute(
            "SELECT * FROM vo2_max WHERE activity_id = 20107340187"
        ).fetchall()
        assert len(vo2_data) == 1

        row = vo2_data[0]
        assert row[0] == 20107340187  # activity_id
        assert abs(row[1] - 44.7) < 0.1  # precise_value (from vo2MaxPreciseValue)
        assert abs(row[2] - 45.0) < 0.1  # value (from vo2MaxValue)
        assert str(row[3]) == "2025-08-19"  # date (from calendarDate)
        assert row[4] is None  # fitness_age
        assert row[5] == 0  # category (default)

        conn.close()
