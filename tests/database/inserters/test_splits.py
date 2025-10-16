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

        # Verify split data using named columns
        split_data = conn.execute(
            """
            SELECT split_index, distance, pace_seconds_per_km, heart_rate
            FROM splits
            WHERE activity_id = 20464005432
            ORDER BY split_index
            """
        ).fetchall()

        # Verify first split
        split1 = split_data[0]
        assert split1[0] == 1  # split_index
        assert split1[1] == 1.0  # distance
        assert split1[2] == 300  # pace_seconds_per_km
        assert split1[3] == 140  # heart_rate

        # Verify second split
        split2 = split_data[1]
        assert split2[0] == 2  # split_index
        assert split2[1] == 1.0  # distance
        assert split2[2] == 295  # pace_seconds_per_km
        assert split2[3] == 145  # heart_rate

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

    @pytest.fixture
    def sample_raw_splits_file(self, tmp_path):
        """Create sample raw splits.json file."""
        raw_splits_data = {
            "activityId": 20636804823,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 387.504,
                    "startTimeGMT": "2025-10-09T12:50:00.0",
                    "intensityType": "INTERVAL",
                    "averageSpeed": 2.581,
                    "averageHR": 127,
                    "averageRunCadence": 183.59375,
                    "averagePower": 268,
                    "groundContactTime": 251.4,
                    "verticalOscillation": 7.22,
                    "verticalRatio": 8.78,
                    "elevationGain": 2.0,
                    "elevationLoss": 2.0,
                },
                {
                    "lapIndex": 2,
                    "distance": 1000.0,
                    "duration": 390.841,
                    "startTimeGMT": "2025-10-09T12:56:28.0",
                    "intensityType": "INTERVAL",
                    "averageSpeed": 2.559,
                    "averageHR": 144,
                    "averageRunCadence": 187.0,
                    "averagePower": 262,
                    "groundContactTime": 249.3,
                    "verticalOscillation": 7.07,
                    "verticalRatio": 8.68,
                    "elevationGain": 0.0,
                    "elevationLoss": 0.0,
                },
            ],
        }

        raw_splits_file = tmp_path / "splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)

        return raw_splits_file

    @pytest.mark.unit
    def test_insert_splits_raw_data_success(self, sample_raw_splits_file, tmp_path):
        """Test insert_splits with raw data mode (no performance.json)."""
        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file=None,
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_splits_raw_data_db_integration(
        self, sample_raw_splits_file, tmp_path
    ):
        """Test insert_splits with raw data actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file=None,
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check splits data
        splits = conn.execute(
            "SELECT * FROM splits WHERE activity_id = 20636804823 ORDER BY split_index"
        ).fetchall()
        assert len(splits) == 2

        # Verify first split data using named columns
        split_data = conn.execute(
            """
            SELECT
                activity_id, split_index, distance, duration_seconds,
                start_time_gmt, start_time_s, end_time_s, intensity_type,
                role_phase, pace_seconds_per_km, heart_rate, cadence, power,
                ground_contact_time, vertical_oscillation, vertical_ratio,
                elevation_gain, elevation_loss
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """
        ).fetchall()

        split1 = split_data[0]
        assert split1[0] == 20636804823  # activity_id
        assert split1[1] == 1  # split_index
        assert split1[2] == 1.0  # distance (km)
        assert split1[3] == pytest.approx(387.504)  # duration_seconds
        assert split1[4] == "2025-10-09T12:50:00.0"  # start_time_gmt
        assert split1[5] == 0  # start_time_s
        assert split1[6] == 388  # end_time_s
        assert split1[7] == "INTERVAL"  # intensity_type

        # Pace: duration / distance = 387.504s per km
        expected_pace = 387.504
        assert abs(split1[9] - expected_pace) < 1.0  # pace_seconds_per_km
        assert split1[10] == 127  # heart_rate
        assert abs(split1[11] - 183.59375) < 0.1  # cadence
        assert split1[12] == 268  # power
        assert abs(split1[13] - 251.4) < 0.1  # ground_contact_time
        assert abs(split1[14] - 7.22) < 0.01  # vertical_oscillation
        assert abs(split1[15] - 8.78) < 0.01  # vertical_ratio
        assert split1[16] == 2.0  # elevation_gain
        assert split1[17] == 2.0  # elevation_loss

        conn.close()

    @pytest.mark.unit
    def test_insert_splits_raw_data_missing_file(self, tmp_path):
        """Test insert_splits raw mode handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file=None,
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False
