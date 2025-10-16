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

    @pytest.mark.unit
    def test_insert_performance_trends_success(self, sample_raw_splits_file, tmp_path):
        """Test insert_performance_trends inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_performance_trends_missing_file(self, tmp_path):
        """Test insert_performance_trends handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
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
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_performance_trends_db_integration(
        self, sample_raw_splits_file, tmp_path
    ):
        """Test insert_performance_trends actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
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
            "SELECT * FROM performance_trends WHERE activity_id = 20636804823"
        ).fetchall()
        assert len(perf_trends) == 1

        # Verify data values (fixture has 5 splits with phases)
        row = perf_trends[0]
        assert row[0] == 20636804823  # activity_id
        # pace_consistency will vary based on actual splits - just check it exists
        assert row[1] is not None  # pace_consistency
        assert row[2] is not None  # hr_drift_percentage
        # Check phase data exists (exact values depend on calculation)
        assert row[5] is not None or row[5] == ""  # warmup_splits

        conn.close()

    @pytest.mark.integration
    def test_insert_4phase_performance_trends(self, sample_raw_splits_file, tmp_path):
        """Test insert_performance_trends writes 4-phase interval training data correctly."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))

        # Check 4-phase data
        data = conn.execute(
            """
            SELECT
                warmup_splits,
                warmup_avg_pace_seconds_per_km,
                warmup_avg_hr,
                run_splits,
                run_avg_pace_seconds_per_km,
                run_avg_hr,
                recovery_splits,
                recovery_avg_pace_seconds_per_km,
                recovery_avg_hr,
                cooldown_splits,
                cooldown_avg_pace_seconds_per_km,
                cooldown_avg_hr,
                pace_consistency,
                hr_drift_percentage
            FROM performance_trends
            WHERE activity_id = 20636804823
            """
        ).fetchone()

        assert data is not None
        assert data[0] == "1"  # warmup splits
        assert abs(data[1] - 387.504) < 1.0  # warmup pace
        assert data[2] == 127.0  # warmup HR
        assert data[3] == "2,3"  # run splits
        # run pace: mean([390.841, 388.01]) = 389.4255
        assert abs(data[4] - 389.4255) < 1.0  # run pace
        assert data[5] == 145.0  # run HR (mean of 144 and 146)
        assert data[6] == "4"  # recovery splits
        assert abs(data[7] - 600.0) < 1.0  # recovery pace (500m / 300s = 600s/km)
        assert data[8] == 135.0  # recovery HR
        assert data[9] == "5"  # cooldown splits
        assert abs(data[10] - 500.0) < 1.0  # cooldown pace (500m / 250s = 500s/km)
        assert data[11] == 125.0  # cooldown HR

        conn.close()

    @pytest.fixture
    def sample_raw_splits_file(self, tmp_path):
        """Create sample raw splits.json with intensityType for phase detection."""
        raw_splits_data = {
            "activityId": 20636804823,
            "lapDTOs": [
                # Warmup phase (WARMUP)
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 387.504,
                    "intensityType": "WARMUP",
                    "averageSpeed": 2.581,
                    "averageHR": 127,
                    "averageRunCadence": 183.6,
                    "averagePower": 268,
                },
                # Run phase (INTERVAL/ACTIVE)
                {
                    "lapIndex": 2,
                    "distance": 1000.0,
                    "duration": 390.841,
                    "intensityType": "INTERVAL",
                    "averageSpeed": 2.559,
                    "averageHR": 144,
                    "averageRunCadence": 187.0,
                    "averagePower": 262,
                },
                {
                    "lapIndex": 3,
                    "distance": 1000.0,
                    "duration": 388.01,
                    "intensityType": "INTERVAL",
                    "averageSpeed": 2.577,
                    "averageHR": 146,
                    "averageRunCadence": 186.2,
                    "averagePower": 267,
                },
                # Recovery phase (RECOVERY)
                {
                    "lapIndex": 4,
                    "distance": 500.0,
                    "duration": 300.0,
                    "intensityType": "RECOVERY",
                    "averageSpeed": 1.667,
                    "averageHR": 135,
                    "averageRunCadence": 170.0,
                    "averagePower": 200,
                },
                # Cooldown phase (COOLDOWN)
                {
                    "lapIndex": 5,
                    "distance": 500.0,
                    "duration": 250.0,
                    "intensityType": "COOLDOWN",
                    "averageSpeed": 2.0,
                    "averageHR": 125,
                    "averageRunCadence": 175.0,
                    "averagePower": 220,
                },
            ],
        }

        raw_splits_file = tmp_path / "splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)

        return raw_splits_file

    @pytest.mark.unit
    def test_insert_performance_trends_raw_data_success(
        self, sample_raw_splits_file, tmp_path
    ):
        """Test insert_performance_trends with raw data mode."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_performance_trends_raw_data_db_integration(
        self, sample_raw_splits_file, tmp_path
    ):
        """Test insert_performance_trends with raw data actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check 4-phase data
        data = conn.execute(
            """
            SELECT
                warmup_splits,
                warmup_avg_pace_seconds_per_km,
                warmup_avg_hr,
                run_splits,
                run_avg_pace_seconds_per_km,
                run_avg_hr,
                recovery_splits,
                recovery_avg_pace_seconds_per_km,
                recovery_avg_hr,
                cooldown_splits,
                cooldown_avg_pace_seconds_per_km,
                cooldown_avg_hr,
                pace_consistency,
                hr_drift_percentage
            FROM performance_trends
            WHERE activity_id = 20636804823
            """
        ).fetchone()

        assert data is not None
        assert data[0] == "1"  # warmup splits
        assert abs(data[1] - 387.504) < 1.0  # warmup pace
        assert data[2] == 127.0  # warmup HR
        assert data[3] == "2,3"  # run splits
        # run pace: mean([390.841, 388.01]) = 389.4255
        assert abs(data[4] - 389.4255) < 1.0  # run pace
        assert data[5] == 145.0  # run HR (mean of 144 and 146)
        assert data[6] == "4"  # recovery splits
        assert abs(data[7] - 600.0) < 1.0  # recovery pace (500m / 300s = 600s/km)
        assert data[8] == 135.0  # recovery HR
        assert data[9] == "5"  # cooldown splits
        assert abs(data[10] - 500.0) < 1.0  # cooldown pace (500m / 250s = 500s/km)
        assert data[11] == 125.0  # cooldown HR

        conn.close()

    @pytest.mark.unit
    def test_insert_performance_trends_raw_data_missing_file(self, tmp_path):
        """Test insert_performance_trends raw mode handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_performance_trends(
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False
