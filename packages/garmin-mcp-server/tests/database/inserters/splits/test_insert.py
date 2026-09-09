"""insert_splits(): success, missing file, invalid laps, DB integration, role/phase, time-range columns, raw-data path."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.splits import insert_splits
from tests.database.inserters.splits._helpers import _eight_lap_splits_data


class TestInsertSplits:
    @pytest.mark.unit
    def test_insert_splits_success(self, sample_raw_splits_file, initialized_db_path):
        """Test insert_splits inserts data successfully."""
        # Setup: Create temporary DuckDB
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )
        conn.close()

        # Verify
        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_splits_missing_file(self, tmp_path):
        """Test insert_splits handles missing file."""
        conn = duckdb.connect(":memory:")

        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file="/nonexistent/splits.json",
        )
        conn.close()

        assert result is False

    @pytest.mark.unit
    def test_insert_splits_no_split_metrics(self, tmp_path):
        """Test insert_splits handles missing lapDTOs."""
        # Create splits file without lapDTOs
        splits_data = {"activityId": 12345}
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        conn = duckdb.connect(":memory:")

        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )
        conn.close()

        assert result is False

    @pytest.mark.unit
    def test_insert_splits_skips_invalid_split_and_inserts_rest(
        self, tmp_path, initialized_db_path, caplog
    ):
        """A single below-floor-cadence split is skipped; the rest are inserted."""
        activity_id = 869001
        raw_data = _eight_lap_splits_data(activity_id, invalid_lap_cadence=5)
        raw_file = tmp_path / "splits.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f)

        conn = duckdb.connect(str(initialized_db_path))

        with caplog.at_level("WARNING"):
            result = insert_splits(
                activity_id=activity_id,
                conn=conn,
                raw_splits_file=str(raw_file),
            )

        assert result is True

        count = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = ?", [activity_id]
        ).fetchone()
        assert count is not None
        assert count[0] == 7  # lap 5 skipped, 7 remain

        # The skipped split (split_index 5) must be absent
        indexes = conn.execute(
            "SELECT split_index FROM splits WHERE activity_id = ? ORDER BY split_index",
            [activity_id],
        ).fetchall()
        assert 5 not in [row[0] for row in indexes]

        # A warning was logged for the skipped split
        assert any("Skipping invalid split" in rec.message for rec in caplog.records)

        conn.close()

    @pytest.mark.unit
    def test_insert_splits_all_valid_inserts_all(self, tmp_path, initialized_db_path):
        """8 valid splits including a 92.95 spm walk lap all insert."""
        activity_id = 869002
        raw_data = _eight_lap_splits_data(activity_id)
        raw_file = tmp_path / "splits.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f)

        conn = duckdb.connect(str(initialized_db_path))

        result = insert_splits(
            activity_id=activity_id,
            conn=conn,
            raw_splits_file=str(raw_file),
        )

        assert result is True

        count = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = ?", [activity_id]
        ).fetchone()
        assert count is not None
        assert count[0] == 8

        # The walk lap (split_index 5) is stored with its low cadence
        walk = conn.execute(
            "SELECT cadence FROM splits WHERE activity_id = ? AND split_index = 5",
            [activity_id],
        ).fetchone()
        assert walk is not None
        assert walk[0] == pytest.approx(92.95, rel=0.01)

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_db_integration(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits actually writes to DuckDB."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Check splits table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "splits" in table_names

        # Check splits data
        splits = conn.execute(
            "SELECT * FROM splits WHERE activity_id = 20636804823 ORDER BY split_index"
        ).fetchall()
        assert len(splits) == 2

        # Verify split data using named columns
        split_data = conn.execute("""
            SELECT split_index, distance, pace_seconds_per_km, heart_rate
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """).fetchall()

        # Verify first split (fixture data)
        split1 = split_data[0]
        assert split1[0] == 1  # split_index
        assert split1[1] == 1.0  # distance (km)
        assert abs(split1[2] - 387.504) < 1.0  # pace_seconds_per_km
        assert split1[3] == 127  # heart_rate

        # Verify second split (fixture data)
        split2 = split_data[1]
        assert split2[0] == 2  # split_index
        assert split2[1] == 1.0  # distance (km)
        assert abs(split2[2] - 390.841) < 1.0  # pace_seconds_per_km
        assert split2[3] == 144  # heart_rate

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_with_role_phase(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits correctly inserts role_phase data (4-phase support)."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        splits = conn.execute("""
            SELECT split_index, role_phase
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 2

        # Verify role_phase values (fixture has INTERVAL intensityType for both splits)
        # INTERVAL maps to "run" phase
        assert splits[0][1] == "run"  # split 1 - INTERVAL
        assert splits[1][1] == "run"  # split 2 - INTERVAL

        conn.close()

    @pytest.mark.unit
    def test_insert_splits_with_time_range_columns(self, tmp_path, initialized_db_path):
        """Test insert_splits includes new time range columns (Phase 1).

        New columns:
        - duration_seconds
        - start_time_gmt
        - start_time_s
        - end_time_s
        - intensity_type
        """
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

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(raw_splits_file),
        )

        assert result is True

        # Query with new columns
        splits = conn.execute("""
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
            """).fetchall()

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

    @pytest.mark.integration
    def test_insert_splits_raw_data_db_integration(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits with raw data actually writes to DuckDB."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Check splits data
        splits = conn.execute(
            "SELECT * FROM splits WHERE activity_id = 20636804823 ORDER BY split_index"
        ).fetchall()
        assert len(splits) == 2

        # Verify first split data using named columns
        split_data = conn.execute("""
            SELECT
                activity_id, split_index, distance, duration_seconds,
                start_time_gmt, start_time_s, end_time_s, intensity_type,
                role_phase, pace_seconds_per_km, heart_rate, cadence, power,
                ground_contact_time, vertical_oscillation, vertical_ratio,
                elevation_gain, elevation_loss
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """).fetchall()

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
