"""
Tests for PerformanceDataInserter

Test coverage:
- Unit tests for insert_performance_data function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.performance import insert_performance_data


class TestPerformanceDataInserter:
    """Test suite for PerformanceDataInserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 1500,
                "avg_pace_seconds_per_km": 300,
                "avg_heart_rate": 145,
            },
            "heart_rate_zones": {
                "zone1": {"low": 100, "secs_in_zone": 300},
                "zone2": {"low": 120, "secs_in_zone": 600},
            },
            "hr_efficiency_analysis": {
                "avg_heart_rate": 145,
                "training_type": "tempo_run",
            },
            "form_efficiency_summary": {
                "gct_stats": {"average": 235},
                "vo_stats": {"average": 7.5},
            },
            "performance_trends": {
                "warmup_phase": {"avg_pace": 310},
                "main_phase": {"avg_pace": 295},
            },
        }

        performance_file = tmp_path / "20464005432.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_performance_data_success(self, sample_performance_file, tmp_path):
        """Test insert_performance_data inserts data successfully."""
        # Setup: Create temporary DuckDB
        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_performance_data(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            activity_date="2025-09-22",
            db_path=str(db_path),
        )

        # Verify
        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_performance_data_missing_file(self, tmp_path):
        """Test insert_performance_data handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_data(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            activity_date="2025-09-22",
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_performance_data_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_performance_data actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_performance_data(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            activity_date="2025-09-22",
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check activities table
        activities = conn.execute(
            "SELECT * FROM activities WHERE activity_id = 20464005432"
        ).fetchall()
        assert len(activities) == 1
        assert (
            str(activities[0][1]) == "2025-09-22"
        )  # activity_date (datetime.date → str)

        # Check performance_data table
        performance = conn.execute(
            "SELECT * FROM performance_data WHERE activity_id = 20464005432"
        ).fetchall()
        assert len(performance) == 1

        conn.close()
