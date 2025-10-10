"""
Tests for Splits Inserter

Test coverage:
- Unit tests for insert_splits function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.splits import insert_splits


class TestSplitsInserter:
    """Test suite for Splits Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with split_metrics."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 1500,
            },
            "split_metrics": [
                {
                    "split_number": 1,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 300,
                    "avg_heart_rate": 140,
                    "avg_cadence": 170,
                    "avg_power": 250,
                    "ground_contact_time_ms": 240,
                    "vertical_oscillation_cm": 7.5,
                    "vertical_ratio_percent": 8.5,
                    "elevation_gain_m": 5,
                    "elevation_loss_m": 2,
                    "terrain_type": "平坦",
                    "role_phase": "warmup",
                },
                {
                    "split_number": 2,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 295,
                    "avg_heart_rate": 145,
                    "avg_cadence": 172,
                    "avg_power": 255,
                    "ground_contact_time_ms": 238,
                    "vertical_oscillation_cm": 7.3,
                    "vertical_ratio_percent": 8.3,
                    "elevation_gain_m": 3,
                    "elevation_loss_m": 4,
                    "terrain_type": "平坦",
                    "role_phase": "run",
                },
            ],
        }

        performance_file = tmp_path / "20464005432.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_splits_success(self, sample_performance_file, tmp_path):
        """Test insert_splits inserts data successfully."""
        # Setup: Create temporary DuckDB
        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        # Verify
        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_splits_missing_file(self, tmp_path):
        """Test insert_splits handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_splits_no_split_metrics(self, tmp_path):
        """Test insert_splits handles missing split_metrics."""
        # Create performance file without split_metrics
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_splits_db_integration(self, sample_performance_file, tmp_path):
        """Test insert_splits actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check splits table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "splits" in table_names

        # Check splits data
        splits = conn.execute(
            "SELECT * FROM splits WHERE activity_id = 20464005432 ORDER BY split_index"
        ).fetchall()
        assert len(splits) == 2

        # Verify first split data (column indices adjusted for new time range columns)
        split1 = splits[0]
        assert split1[0] == 20464005432  # activity_id
        assert split1[1] == 1  # split_index
        assert split1[2] == 1.0  # distance
        assert split1[10] == 300  # pace_seconds_per_km (index 10 after new columns)
        assert split1[11] == 140  # heart_rate (index 11 after new columns)

        # Verify second split data
        split2 = splits[1]
        assert split2[0] == 20464005432  # activity_id
        assert split2[1] == 2  # split_index
        assert split2[2] == 1.0  # distance
        assert split2[10] == 295  # pace_seconds_per_km (index 10 after new columns)
        assert split2[11] == 145  # heart_rate (index 11 after new columns)

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_with_role_phase(self, sample_performance_file, tmp_path):
        """Test insert_splits correctly inserts role_phase data (4-phase support)."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        assert result is True

        # Verify role_phase data
        conn = duckdb.connect(str(db_path))

        splits = conn.execute(
            """
            SELECT split_index, role_phase
            FROM splits
            WHERE activity_id = 20464005432
            ORDER BY split_index
            """
        ).fetchall()

        assert len(splits) == 2

        # Verify role_phase values
        assert splits[0][1] == "warmup"  # split 1
        assert splits[1][1] == "run"  # split 2

        conn.close()

    @pytest.mark.unit
    def test_insert_splits_with_time_range_columns(self, tmp_path):
        """Test insert_splits includes new time range columns (Phase 1).

        New columns:
        - duration_seconds
        - start_time_gmt
        - start_time_s
        - end_time_s
        - intensity_type
        """
        import duckdb

        # Setup: Create performance.json with split_metrics
        performance_data = {
            "split_metrics": [
                {
                    "split_number": 1,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 387,
                    "avg_heart_rate": 127,
                    "role_phase": "warmup",
                },
                {
                    "split_number": 2,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 390,
                    "avg_heart_rate": 144,
                    "role_phase": "run",
                },
            ]
        }
        performance_file = tmp_path / "test_perf.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        # Setup: Create raw splits.json with lapDTOs
        raw_splits_data = {
            "activityId": 20636804823,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "duration": 387.504,
                    "startTimeGMT": "2025-10-09T12:50:00.0",
                    "intensityType": "INTERVAL",
                },
                {
                    "lapIndex": 2,
                    "duration": 390.841,
                    "startTimeGMT": "2025-10-09T12:56:28.0",
                    "intensityType": "INTERVAL",
                },
            ],
        }
        raw_splits_file = tmp_path / "splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(performance_file),
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(raw_splits_file),
        )

        assert result is True

        # Verify: Check new columns exist and have correct values
        conn = duckdb.connect(str(db_path))

        # Query with new columns
        splits = conn.execute(
            """
            SELECT
                split_index,
                duration_seconds,
                start_time_gmt,
                start_time_s,
                end_time_s,
                intensity_type
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """
        ).fetchall()

        assert len(splits) == 2

        # Verify split 1
        split1 = splits[0]
        assert split1[0] == 1  # split_index
        assert split1[1] == pytest.approx(387.504, rel=0.01)  # duration_seconds
        assert split1[2] == "2025-10-09T12:50:00.0"  # start_time_gmt
        assert split1[3] == 0  # start_time_s (cumulative: 0)
        assert split1[4] == 388  # end_time_s (cumulative: 0 + round(387.504))
        assert split1[5] == "INTERVAL"  # intensity_type

        # Verify split 2
        split2 = splits[1]
        assert split2[0] == 2  # split_index
        assert split2[1] == pytest.approx(390.841, rel=0.01)  # duration_seconds
        assert split2[2] == "2025-10-09T12:56:28.0"  # start_time_gmt
        assert split2[3] == 388  # start_time_s (cumulative: 388)
        assert split2[4] == 779  # end_time_s (cumulative: 388 + round(390.841))
        assert split2[5] == "INTERVAL"  # intensity_type

        conn.close()
