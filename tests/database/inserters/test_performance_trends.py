"""
Tests for Performance Trends Inserter

Test coverage:
- Unit tests for insert_performance_trends function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.performance_trends import insert_performance_trends


class TestPerformanceTrendsInserter:
    """Test suite for Performance Trends Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with performance_trends."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 22.0,
            },
            "performance_trends": {
                "warmup_phase": {
                    "splits": [1, 2, 3, 4],
                    "avg_pace": 406.67,
                    "avg_hr": 144.5,
                },
                "main_phase": {
                    "splits": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
                    "avg_pace": 469.23,
                    "avg_hr": 151.77,
                },
                "finish_phase": {
                    "splits": [18, 19, 20, 21, 22],
                    "avg_pace": 529.69,
                    "avg_hr": 141.2,
                },
                "pace_consistency": 0.086,
                "hr_drift_percentage": -2.28,
                "cadence_consistency": "高い安定性",
                "fatigue_pattern": "適切な疲労管理",
            },
        }

        performance_file = tmp_path / "20615445009.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_performance_trends_success(self, sample_performance_file, tmp_path):
        """Test insert_performance_trends inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_performance_trends_missing_file(self, tmp_path):
        """Test insert_performance_trends handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_performance_trends_no_data(self, tmp_path):
        """Test insert_performance_trends handles missing performance_trends."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_performance_trends_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_performance_trends actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            performance_file=str(sample_performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check performance_trends table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "performance_trends" in table_names

        # Check performance_trends data
        perf_trends = conn.execute(
            "SELECT * FROM performance_trends WHERE activity_id = 20615445009"
        ).fetchall()
        assert len(perf_trends) == 1

        # Verify data values
        row = perf_trends[0]
        assert row[0] == 20615445009  # activity_id
        assert abs(row[1] - 0.086) < 0.001  # pace_consistency
        assert abs(row[2] - (-2.28)) < 0.01  # hr_drift_percentage
        assert row[3] == "高い安定性"  # cadence_consistency
        assert row[4] == "適切な疲労管理"  # fatigue_pattern
        assert row[5] == "1,2,3,4"  # warmup_splits
        assert abs(row[6] - 406.67) < 0.01  # warmup_avg_pace
        assert abs(row[8] - 144.5) < 0.1  # warmup_avg_hr

        conn.close()
