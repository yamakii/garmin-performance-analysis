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
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with hr_efficiency_analysis."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
            },
            "hr_efficiency_analysis": {
                "avg_heart_rate": 148.04545454545453,
                "training_type": "threshold_work",
                "hr_stability": "変動あり",
                "description": "適切な心拍ゾーンで実施",
            },
        }

        performance_file = tmp_path / "20615445009.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_hr_efficiency_success(self, sample_performance_file, tmp_path):
        """Test insert_hr_efficiency inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_hr_efficiency_missing_file(self, tmp_path):
        """Test insert_hr_efficiency handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_hr_efficiency_no_data(self, tmp_path):
        """Test insert_hr_efficiency handles missing hr_efficiency_analysis."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_hr_efficiency_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_hr_efficiency actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_hr_efficiency(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
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
        assert row[3] == "変動あり"  # hr_stability

        conn.close()
