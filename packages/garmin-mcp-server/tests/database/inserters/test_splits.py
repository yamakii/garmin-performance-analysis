"""
Tests for Splits Inserter

Test coverage:
- Unit tests for insert_splits function
- Integration tests with DuckDB
"""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.splits import insert_splits
from garmin_mcp.database.inserters.splits_helpers.cadence_power import (
    CadencePowerCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.environmental import (
    EnvironmentalCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.extractor import SplitsExtractor
from garmin_mcp.database.inserters.splits_helpers.hr_calculations import HRCalculator
from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper


class TestSplitsInserter:
    """Test suite for Splits Inserter."""

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

    @pytest.fixture
    def sample_raw_splits_file(self, tmp_path):
        """Create sample raw splits.json file with all new fields."""
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
                    # New fields for Phase 1
                    "strideLength": 91.28,
                    "maxHR": 148,
                    "maxRunCadence": 184.0,
                    "maxPower": 413,
                    "normalizedPower": 270,
                    "avgGradeAdjustedSpeed": 2.55,
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
                    # New fields for Phase 1
                    "strideLength": 89.5,
                    "maxHR": 152,
                    "maxRunCadence": 189.0,
                    "maxPower": 390,
                    "normalizedPower": 265,
                    "avgGradeAdjustedSpeed": 2.52,
                },
            ],
        }

        raw_splits_file = tmp_path / "splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)

        return raw_splits_file

    @pytest.mark.unit
    def test_insert_splits_raw_data_success(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits with raw data mode (no performance.json)."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )
        conn.close()

        assert result is True
        assert db_path.exists()

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

    @pytest.mark.unit
    def test_insert_splits_raw_data_missing_file(self, tmp_path):
        """Test insert_splits raw mode handles missing files."""
        conn = duckdb.connect(":memory:")

        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file="/nonexistent/splits.json",
        )
        conn.close()

        assert result is False

    # ===== NEW TESTS FOR PHASE 1: Add 7 Missing Performance Metrics =====

    @pytest.mark.unit
    def test_extract_splits_includes_stride_length(self, tmp_path):
        """Test SplitsExtractor.extract_splits_from_raw() extracts stride_length field."""

        # Create test data with strideLength
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "strideLength": 91.28,  # cm
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(splits_file))

        # Verify
        assert splits is not None
        assert len(splits) == 1
        assert "stride_length_cm" in splits[0]
        assert splits[0]["stride_length_cm"] == 91.28

    @pytest.mark.unit
    def test_extract_splits_includes_max_metrics(self, tmp_path):
        """Test SplitsExtractor.extract_splits_from_raw() extracts max_heart_rate, max_cadence, max_power."""

        # Create test data with max metrics
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "maxHR": 148,
                    "maxRunCadence": 184.0,
                    "maxPower": 413,
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(splits_file))

        # Verify
        assert splits is not None
        assert len(splits) == 1
        assert "max_heart_rate" in splits[0]
        assert "max_cadence" in splits[0]
        assert "max_power" in splits[0]
        assert splits[0]["max_heart_rate"] == 148
        assert splits[0]["max_cadence"] == 184.0
        assert splits[0]["max_power"] == 413

    @pytest.mark.unit
    def test_extract_splits_includes_power_metrics(self, tmp_path):
        """Test SplitsExtractor.extract_splits_from_raw() extracts normalized_power."""

        # Create test data with normalized power
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "normalizedPower": 270,
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(splits_file))

        # Verify
        assert splits is not None
        assert len(splits) == 1
        assert "normalized_power" in splits[0]
        assert splits[0]["normalized_power"] == 270

    @pytest.mark.unit
    def test_extract_splits_includes_speed_metrics(self, tmp_path):
        """Test SplitsExtractor.extract_splits_from_raw() extracts average_speed and grade_adjusted_speed."""

        # Create test data with speed metrics
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "averageSpeed": 2.69,
                    "avgGradeAdjustedSpeed": 2.55,
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(splits_file))

        # Verify
        assert splits is not None
        assert len(splits) == 1
        assert "average_speed_mps" in splits[0]
        assert "grade_adjusted_speed_mps" in splits[0]
        assert splits[0]["average_speed_mps"] == 2.69
        assert splits[0]["grade_adjusted_speed_mps"] == 2.55

    @pytest.mark.unit
    def test_extract_splits_handles_missing_fields(self, tmp_path):
        """Test SplitsExtractor.extract_splits_from_raw() handles missing new fields gracefully (NULL)."""

        # Create test data WITHOUT new fields (simulate older activity)
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    # No strideLength, maxHR, etc.
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(splits_file))

        # Verify - should return None for missing fields, not error
        assert splits is not None
        assert len(splits) == 1
        assert splits[0]["stride_length_cm"] is None
        assert splits[0]["max_heart_rate"] is None
        assert splits[0]["max_cadence"] is None
        assert splits[0]["max_power"] is None
        assert splits[0]["normalized_power"] is None
        assert splits[0]["average_speed_mps"] is None
        assert splits[0]["grade_adjusted_speed_mps"] is None

    @pytest.mark.unit
    def test_extract_splits_preserves_existing_fields(self, sample_raw_splits_file):
        """Test SplitsExtractor.extract_splits_from_raw() still extracts all 19 existing fields correctly."""

        # Execute
        splits = SplitsExtractor.extract_splits_from_raw(str(sample_raw_splits_file))

        # Verify existing fields still present
        assert splits is not None
        assert len(splits) == 2

        split1 = splits[0]
        # Check all 19 existing fields
        assert "split_number" in split1
        assert "distance_km" in split1
        assert "duration_seconds" in split1
        assert "start_time_gmt" in split1
        assert "start_time_s" in split1
        assert "end_time_s" in split1
        assert "intensity_type" in split1
        assert "role_phase" in split1
        assert "pace_str" in split1
        assert "pace_seconds_per_km" in split1
        assert "avg_heart_rate" in split1
        assert "avg_cadence" in split1
        assert "avg_power" in split1
        assert "ground_contact_time_ms" in split1
        assert "vertical_oscillation_cm" in split1
        assert "vertical_ratio_percent" in split1
        assert "elevation_gain_m" in split1
        assert "elevation_loss_m" in split1
        assert "terrain_type" in split1

        # Verify values match fixture
        assert split1["split_number"] == 1
        assert split1["distance_km"] == 1.0
        assert split1["avg_heart_rate"] == 127

    # ===== PHASE 2: Database Insertion Tests =====

    @pytest.mark.integration
    def test_insert_splits_creates_new_columns(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits creates 6 new columns in DuckDB (stride_length already exists)."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Get column names
        columns_query = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'splits' ORDER BY column_name"
        ).fetchall()
        column_names = [col[0] for col in columns_query]

        # Verify 6 new columns exist (stride_length already exists)
        assert "max_heart_rate" in column_names
        assert "max_cadence" in column_names
        assert "max_power" in column_names
        assert "normalized_power" in column_names
        assert "average_speed" in column_names
        assert "grade_adjusted_speed" in column_names

        # Verify stride_length column already exists
        assert "stride_length" in column_names

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_populates_new_fields(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits populates all 7 new fields with correct values."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        split_data = conn.execute("""
            SELECT
                split_index,
                stride_length,
                max_heart_rate,
                max_cadence,
                max_power,
                normalized_power,
                average_speed,
                grade_adjusted_speed
            FROM splits
            WHERE activity_id = 20636804823
            ORDER BY split_index
            """).fetchall()

        assert len(split_data) == 2

        # Verify split 1 (from fixture)
        split1 = split_data[0]
        assert split1[0] == 1  # split_index
        assert split1[1] == pytest.approx(91.28, rel=0.01)  # stride_length
        assert split1[2] == 148  # max_heart_rate
        assert split1[3] == pytest.approx(184.0, rel=0.01)  # max_cadence
        assert split1[4] == pytest.approx(413, rel=0.01)  # max_power
        assert split1[5] == pytest.approx(270, rel=0.01)  # normalized_power
        assert split1[6] == pytest.approx(2.581, rel=0.01)  # average_speed
        assert split1[7] == pytest.approx(2.55, rel=0.01)  # grade_adjusted_speed

        # Verify split 2 (from fixture)
        split2 = split_data[1]
        assert split2[0] == 2  # split_index
        assert split2[1] == pytest.approx(89.5, rel=0.01)  # stride_length
        assert split2[2] == 152  # max_heart_rate
        assert split2[3] == pytest.approx(189.0, rel=0.01)  # max_cadence
        assert split2[4] == pytest.approx(390, rel=0.01)  # max_power
        assert split2[5] == pytest.approx(265, rel=0.01)  # normalized_power
        assert split2[6] == pytest.approx(2.559, rel=0.01)  # average_speed
        assert split2[7] == pytest.approx(2.52, rel=0.01)  # grade_adjusted_speed

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_handles_partial_fields(self, tmp_path, initialized_db_path):
        """Test insert_splits handles partial fields (some new fields NULL)."""
        # Create test data with only some new fields
        raw_splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "averageHR": 140,
                    # Only some new fields present
                    "strideLength": 90.0,
                    "maxHR": 150,
                    # Missing: maxRunCadence, maxPower, normalizedPower, averageSpeed, avgGradeAdjustedSpeed
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        split_data = conn.execute("""
            SELECT
                stride_length,
                max_heart_rate,
                max_cadence,
                max_power,
                normalized_power,
                average_speed,
                grade_adjusted_speed
            FROM splits
            WHERE activity_id = 12345
            """).fetchone()
        assert split_data is not None

        # Present fields should have values
        assert split_data[0] == pytest.approx(90.0)  # stride_length
        assert split_data[1] == 150  # max_heart_rate

        # Missing fields should be NULL
        assert split_data[2] is None  # max_cadence
        assert split_data[3] is None  # max_power
        assert split_data[4] is None  # normalized_power
        assert split_data[5] is None  # average_speed
        assert split_data[6] is None  # grade_adjusted_speed

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_with_real_activity_data(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_splits with real-like activity data containing all 7 new fields."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Count non-NULL values for new fields
        stats = conn.execute("""
            SELECT
                COUNT(*) as total_splits,
                COUNT(stride_length) as stride_populated,
                COUNT(max_heart_rate) as max_hr_populated,
                COUNT(max_cadence) as max_cad_populated,
                COUNT(max_power) as max_pow_populated,
                COUNT(normalized_power) as norm_pow_populated,
                COUNT(average_speed) as avg_spd_populated,
                COUNT(grade_adjusted_speed) as grade_adj_populated
            FROM splits
            WHERE activity_id = 20636804823
            """).fetchone()
        assert stats is not None

        # All 2 splits should have all 7 new fields
        assert stats[0] == 2  # total_splits
        assert stats[1] == 2  # stride_populated
        assert stats[2] == 2  # max_hr_populated
        assert stats[3] == 2  # max_cad_populated
        assert stats[4] == 2  # max_pow_populated
        assert stats[5] == 2  # norm_pow_populated
        assert stats[6] == 2  # avg_spd_populated
        assert stats[7] == 2  # grade_adj_populated

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_multiple_activities(self, tmp_path, initialized_db_path):
        """Test insert_splits with 3 activities with different field availability."""

        # Activity 1: All fields present
        activity1_data = {
            "activityId": 1,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "strideLength": 91.0,
                    "maxHR": 150,
                    "maxRunCadence": 185.0,
                    "maxPower": 400,
                    "normalizedPower": 280,
                    "averageSpeed": 2.7,
                    "avgGradeAdjustedSpeed": 2.6,
                }
            ],
        }

        # Activity 2: No power metrics
        activity2_data = {
            "activityId": 2,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "strideLength": 90.0,
                    "maxHR": 145,
                    "maxRunCadence": 180.0,
                    "averageSpeed": 2.65,
                    # No maxPower, normalizedPower, avgGradeAdjustedSpeed
                }
            ],
        }

        # Activity 3: Only stride_length and max_hr
        activity3_data = {
            "activityId": 3,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "strideLength": 88.0,
                    "maxHR": 140,
                    # No cadence, power, speed metrics
                }
            ],
        }

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Insert all 3 activities
        for activity_data in [activity1_data, activity2_data, activity3_data]:
            activity_file = tmp_path / f"splits_{activity_data['activityId']}.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            result = insert_splits(
                activity_id=int(activity_data["activityId"]),  # type: ignore[call-overload]
                conn=conn,
                raw_splits_file=str(activity_file),
            )
            assert result is True

        # Activity 1: All fields present
        act1 = conn.execute(
            "SELECT stride_length, max_heart_rate, max_power, normalized_power FROM splits WHERE activity_id = 1"
        ).fetchone()
        assert act1 is not None
        assert act1[0] == pytest.approx(91.0)
        assert act1[1] == 150
        assert act1[2] == pytest.approx(400)
        assert act1[3] == pytest.approx(280)

        # Activity 2: No power metrics
        act2 = conn.execute(
            "SELECT stride_length, max_heart_rate, max_power, normalized_power FROM splits WHERE activity_id = 2"
        ).fetchone()
        assert act2 is not None
        assert act2[0] == pytest.approx(90.0)
        assert act2[1] == 145
        assert act2[2] is None  # No power data
        assert act2[3] is None

        # Activity 3: Only stride_length and max_hr
        act3 = conn.execute(
            "SELECT stride_length, max_heart_rate, max_cadence FROM splits WHERE activity_id = 3"
        ).fetchone()
        assert act3 is not None
        assert act3[0] == pytest.approx(88.0)
        assert act3[1] == 140
        assert act3[2] is None  # No cadence data

        conn.close()

    # ===== PHASE 3: Validation Tests =====

    @pytest.mark.integration
    def test_field_population_rates(self, tmp_path, initialized_db_path):
        """Test field population rates for new fields across multiple activities."""

        # Create 3 activities with different field coverage
        activities = [
            {
                "activityId": 1,
                "lapDTOs": [
                    {
                        "lapIndex": 1,
                        "distance": 1000.0,
                        "duration": 300.0,
                        "strideLength": 91.0,
                        "maxHR": 150,
                        "maxRunCadence": 185.0,
                        "maxPower": 400,
                        "normalizedPower": 280,
                        "averageSpeed": 2.7,
                        "avgGradeAdjustedSpeed": 2.6,
                    }
                ],
            },
            {
                "activityId": 2,
                "lapDTOs": [
                    {
                        "lapIndex": 1,
                        "distance": 1000.0,
                        "duration": 300.0,
                        "strideLength": 90.0,
                        "maxHR": 145,
                        "maxRunCadence": 180.0,
                        "averageSpeed": 2.65,
                        # No power metrics
                    }
                ],
            },
            {
                "activityId": 3,
                "lapDTOs": [
                    {
                        "lapIndex": 1,
                        "distance": 1000.0,
                        "duration": 300.0,
                        "strideLength": 88.0,
                        "maxHR": 140,
                        # Minimal fields
                    }
                ],
            },
        ]

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Insert all activities
        for activity_data in activities:
            activity_file = tmp_path / f"splits_{activity_data['activityId']}.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            result = insert_splits(
                activity_id=int(activity_data["activityId"]),  # type: ignore[call-overload]
                conn=conn,
                raw_splits_file=str(activity_file),
            )
            assert result is True

        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(stride_length) * 100.0 / COUNT(*) as stride_pct,
                COUNT(max_heart_rate) * 100.0 / COUNT(*) as max_hr_pct,
                COUNT(max_power) * 100.0 / COUNT(*) as power_pct,
                COUNT(grade_adjusted_speed) * 100.0 / COUNT(*) as grade_adj_pct
            FROM splits
            """).fetchone()
        assert stats is not None

        # Verify population rates
        assert stats[0] == 3  # total_splits
        assert stats[1] == 100.0  # stride_pct (all 3 activities)
        assert stats[2] == 100.0  # max_hr_pct (all 3 activities)
        assert stats[3] == pytest.approx(33.33, rel=0.1)  # power_pct (1 of 3)
        assert stats[4] == pytest.approx(33.33, rel=0.1)  # grade_adj_pct (1 of 3)

        conn.close()

    @pytest.mark.integration
    def test_max_metrics_validity(self, sample_raw_splits_file, initialized_db_path):
        """Test that max metrics are >= avg metrics (data integrity check)."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Check max_heart_rate >= heart_rate
        hr_checks = conn.execute("""
            SELECT
                split_index,
                heart_rate,
                max_heart_rate,
                max_heart_rate >= heart_rate as hr_valid
            FROM splits
            WHERE activity_id = 20636804823
              AND heart_rate IS NOT NULL
              AND max_heart_rate IS NOT NULL
            """).fetchall()

        for split_index, avg_hr, max_hr, hr_valid in hr_checks:
            assert (
                hr_valid
            ), f"Split {split_index}: max_hr ({max_hr}) < avg_hr ({avg_hr})"

        # Check max_cadence >= cadence
        cadence_checks = conn.execute("""
            SELECT
                split_index,
                cadence,
                max_cadence,
                max_cadence >= cadence as cadence_valid
            FROM splits
            WHERE activity_id = 20636804823
              AND cadence IS NOT NULL
              AND max_cadence IS NOT NULL
            """).fetchall()

        for split_index, avg_cad, max_cad, cad_valid in cadence_checks:
            assert (
                cad_valid
            ), f"Split {split_index}: max_cad ({max_cad}) < avg_cad ({avg_cad})"

        # Check max_power >= power (if both present)
        power_checks = conn.execute("""
            SELECT
                split_index,
                power,
                max_power,
                max_power >= power as power_valid
            FROM splits
            WHERE activity_id = 20636804823
              AND power IS NOT NULL
              AND max_power IS NOT NULL
            """).fetchall()

        for split_index, avg_pow, max_pow, pow_valid in power_checks:
            assert (
                pow_valid
            ), f"Split {split_index}: max_pow ({max_pow}) < avg_pow ({avg_pow})"

        conn.close()

    @pytest.mark.unit
    def test_calculate_hr_zone_mapping(self):
        """Test HR zone calculation from heart rate value.

        RED Phase: This test will fail because _calculate_hr_zone doesn't exist yet.
        """

        # Test data: Typical HR zones for a runner
        hr_zones = [
            {"zone_number": 1, "lower_bpm": 100, "upper_bpm": 120},
            {"zone_number": 2, "lower_bpm": 120, "upper_bpm": 150},
            {"zone_number": 3, "lower_bpm": 150, "upper_bpm": 165},
            {"zone_number": 4, "lower_bpm": 165, "upper_bpm": 180},
            {"zone_number": 5, "lower_bpm": 180, "upper_bpm": 195},
        ]

        # Test zone mapping
        assert HRCalculator.calculate_hr_zone(110, hr_zones) == "Zone 1"
        assert HRCalculator.calculate_hr_zone(145, hr_zones) == "Zone 2"
        assert HRCalculator.calculate_hr_zone(160, hr_zones) == "Zone 3"
        assert HRCalculator.calculate_hr_zone(170, hr_zones) == "Zone 4"
        assert HRCalculator.calculate_hr_zone(185, hr_zones) == "Zone 5"

        # Test edge cases
        assert (
            HRCalculator.calculate_hr_zone(95, hr_zones) == "Zone 0 (Recovery)"
        )  # Below Zone 1
        assert (
            HRCalculator.calculate_hr_zone(200, hr_zones) == "Zone 5+ (Max)"
        )  # Above Zone 5

        # Test boundary values
        assert HRCalculator.calculate_hr_zone(120, hr_zones) in [
            "Zone 1",
            "Zone 2",
        ]  # Boundary

        # Test None handling
        assert HRCalculator.calculate_hr_zone(None, hr_zones) is None

    @pytest.mark.unit
    def test_calculate_cadence_rating(self):
        """Test cadence rating evaluation.

        RED Phase: This test will fail because _calculate_cadence_rating doesn't exist yet.
        """

        # Test ratings based on scientific thresholds
        assert (
            CadencePowerCalculator.calculate_cadence_rating(165)
            == "Low (165 spm, target 180+)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(175) == "Good (175 spm)"
        assert (
            CadencePowerCalculator.calculate_cadence_rating(185)
            == "Excellent (185 spm)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(192) == "Elite (192 spm)"

        # Test boundary values
        assert CadencePowerCalculator.calculate_cadence_rating(170) == "Good (170 spm)"
        assert (
            CadencePowerCalculator.calculate_cadence_rating(180)
            == "Excellent (180 spm)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(190) == "Elite (190 spm)"

        # Test None handling
        assert CadencePowerCalculator.calculate_cadence_rating(None) is None

    @pytest.mark.unit
    def test_calculate_power_efficiency(self):
        """Test power efficiency (W/kg) calculation."""

        # Test various power/weight ratios
        # 170/70 = 2.43 (Low, <2.5)
        # 200/70 = 2.86 (Moderate, 2.5-3.5)
        # 250/70 = 3.57 (Good, 3.5-4.5)
        # 350/70 = 5.0 (Excellent, >=4.5)
        assert (
            CadencePowerCalculator.calculate_power_efficiency(170, 70)
            == "Low (2.4 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(200, 70)
            == "Moderate (2.9 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(250, 70)
            == "Good (3.6 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(350, 70)
            == "Excellent (5.0 W/kg)"
        )

        # Test None handling
        assert CadencePowerCalculator.calculate_power_efficiency(None, 70) is None
        assert CadencePowerCalculator.calculate_power_efficiency(250, None) is None
        assert CadencePowerCalculator.calculate_power_efficiency(None, None) is None

    @pytest.mark.unit
    def test_calculate_environmental_conditions(self):
        """Test environmental conditions summary."""

        # Test various conditions
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(15, 2, 65)
            == "Cool (15°C), Calm"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(28, 12, 85)
            == "Hot (28°C), Breezy (12 km/h), Humid (85%)"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(8, 20, 25)
            == "Cold (8°C), Windy (20 km/h), Dry (25%)"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(20, None, None)
            == "Mild (20°C)"
        )

        # Test None handling
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(None, 10, 50)
            is None
        )

    @pytest.mark.unit
    def test_calculate_wind_impact(self):
        """Test wind impact evaluation."""

        # Test wind levels
        assert EnvironmentalCalculator.calculate_wind_impact(3) == "Minimal (<5 km/h)"
        assert (
            EnvironmentalCalculator.calculate_wind_impact(10, None)
            == "Moderate (10 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(20)
            == "Significant (20 km/h, pace impact expected)"
        )

        # Test with direction (headwind/tailwind/crosswind)
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 30)
            == "Moderate headwind (12 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 180)
            == "Moderate tailwind (12 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 90)
            == "Moderate crosswind (12 km/h)"
        )

        # Test None handling
        assert EnvironmentalCalculator.calculate_wind_impact(None) is None

    @pytest.mark.unit
    def test_calculate_temp_impact(self):
        """Test temperature impact based on training type."""

        # Test recovery/low_moderate (wider tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(18, "recovery")
            == "Good (18°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(28, "low_moderate")
            == "Hot (28°C)"
        )

        # Test base/tempo_threshold (moderate tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(15, "tempo_threshold")
            == "Ideal (15°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(25, "tempo_threshold")
            == "Hot (25°C, hydration important)"
        )

        # Test interval_sprint (narrow tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(12, "interval_sprint")
            == "Ideal (12°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(28, "interval_sprint")
            == "Too hot (28°C, consider rescheduling)"
        )

        # Test None handling
        assert EnvironmentalCalculator.calculate_temp_impact(None, "base") is None

    @pytest.mark.unit
    def test_calculate_environmental_impact(self):
        """Test overall environmental impact rating."""

        # Test ideal conditions (score=0)
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Ideal (15°C)", "Minimal (<5 km/h)", 3, 2
            )
            == "Ideal conditions"
        )

        # Test good conditions (score=1-2: Warm(1) + no wind + 30m elevation(0))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Warm (22°C)", "Minimal (<5 km/h)", 15, 15
            )
            == "Good conditions"
        )

        # Test moderate challenge (score=3-4: Hot(2) + Moderate(1) + 40m elevation(0))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Hot (25°C)", "Moderate (10 km/h)", 20, 20
            )
            == "Moderate challenge"
        )

        # Test challenging conditions (score=5: Hot(2) + Moderate(1) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Hot (26°C)", "Moderate headwind (12 km/h)", 60, 60
            )
            == "Challenging conditions"
        )

        # Test extreme conditions (score=6: Too hot(3) + Moderate(1) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Too hot (28°C)", "Moderate (12 km/h)", 60, 60
            )
            == "Extreme conditions"
        )

        # Test extreme conditions (score=7: Too hot(3) + Significant(2) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Too hot (30°C)", "Significant (20 km/h)", 100, 100
            )
            == "Extreme conditions"
        )

    # ===========================================================================
    # Tests for intensity_type estimation (Feature: #40)
    # ===========================================================================

    @pytest.mark.unit
    def test_estimate_intensity_type_warmup_first_two_splits(self):
        """Test WARMUP estimation for first 2 splits."""

        # Test case 1: 10 splits total (first 2 should be WARMUP)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 0 → WARMUP
            {"pace_seconds_per_km": 290, "avg_heart_rate": 145},  # Split 1 → WARMUP
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},  # Split 2 → not warmup
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] != "WARMUP"

    @pytest.mark.unit
    def test_estimate_intensity_type_warmup_single_for_short_run(self):
        """Test WARMUP estimation for short runs (≤6 splits, only first 1)."""

        # Test case: 6 splits total (only first 1 should be WARMUP)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 0 → WARMUP
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},  # Split 1 → not warmup
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] != "WARMUP"

    @pytest.mark.unit
    def test_estimate_intensity_type_cooldown_last_two_splits(self):
        """Test COOLDOWN estimation for last 2 splits."""

        # Test case: 10 splits total (last 2 should be COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 290, "avg_heart_rate": 145},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 8 → COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # Split 9 → COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[-2] == "COOLDOWN"
        assert result[-1] == "COOLDOWN"
        assert result[-3] != "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_cooldown_single_for_short_run(self):
        """Test COOLDOWN estimation for short runs (≤6 splits, only last 1)."""

        # Test case: 6 splits total (only last 1 should be COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 5 → COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[-1] == "COOLDOWN"
        assert result[-2] != "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_recovery_after_interval(self):
        """Test RECOVERY estimation (pace >400 AND previous was INTERVAL/RECOVERY)."""

        # Test case: Sprint pattern (WARMUP, INTERVAL, RECOVERY, INTERVAL, RECOVERY, COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {"pace_seconds_per_km": 210, "avg_heart_rate": 180},  # INTERVAL
            {
                "pace_seconds_per_km": 450,
                "avg_heart_rate": 130,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 220, "avg_heart_rate": 185},  # INTERVAL
            {
                "pace_seconds_per_km": 460,
                "avg_heart_rate": 125,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 210, "avg_heart_rate": 180},  # INTERVAL
            {
                "pace_seconds_per_km": 420,
                "avg_heart_rate": 120,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 310, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 320, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"
        assert result[3] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[4] == "INTERVAL"
        assert result[5] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[6] == "INTERVAL"
        assert result[7] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[8] == "COOLDOWN"
        assert result[9] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_interval_by_fast_pace(self):
        """Test INTERVAL estimation by fast pace (pace < avg × 0.90)."""

        # Test case: Threshold run (WARMUP, INTERVAL zone, COOLDOWN)
        # Average pace ≈ 260 sec/km, threshold = 234 sec/km
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {"pace_seconds_per_km": 220, "avg_heart_rate": 175},  # INTERVAL (220 < 234)
            {"pace_seconds_per_km": 230, "avg_heart_rate": 175},  # INTERVAL (230 < 234)
            {"pace_seconds_per_km": 225, "avg_heart_rate": 175},  # INTERVAL (225 < 234)
            {"pace_seconds_per_km": 228, "avg_heart_rate": 175},  # INTERVAL (228 < 234)
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"  # Fast pace
        assert result[3] == "INTERVAL"  # Fast pace
        assert result[4] == "INTERVAL"  # Fast pace
        assert result[5] == "INTERVAL"  # Fast pace
        assert result[6] == "COOLDOWN"
        assert result[7] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_interval_by_high_hr(self):
        """Test INTERVAL estimation by high HR (HR > avg × 1.1)."""

        # Test case: High HR effort
        # Average HR = 153.75 bpm, threshold = 169.125 bpm
        # Only splits with HR >= 170 qualify as INTERVAL
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 170,
            },  # INTERVAL (170 > 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 172,
            },  # INTERVAL (172 > 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 168,
            },  # ACTIVE (168 < 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 165,
            },  # ACTIVE (165 < 169.125)
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"  # High HR (170 > 169.125)
        assert result[3] == "INTERVAL"  # High HR (172 > 169.125)
        assert result[4] == "ACTIVE"  # HR not high enough (168 < 169.125)
        assert result[5] == "ACTIVE"  # HR not high enough (165 < 169.125)
        assert result[6] == "COOLDOWN"
        assert result[7] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_active_default(self):
        """Test ACTIVE estimation as default (doesn't match other rules)."""

        # Test case: Easy run (moderate pace, moderate HR)
        # With 4 splits (≤6), expect: WARMUP, ACTIVE, ACTIVE, COOLDOWN
        splits = [
            {"pace_seconds_per_km": 270, "avg_heart_rate": 145},  # WARMUP (position)
            {"pace_seconds_per_km": 275, "avg_heart_rate": 147},  # ACTIVE
            {"pace_seconds_per_km": 268, "avg_heart_rate": 144},  # ACTIVE
            {"pace_seconds_per_km": 272, "avg_heart_rate": 146},  # COOLDOWN (position)
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Position-based rules apply first for runs ≤6 splits
        assert result[0] == "WARMUP"  # First split
        assert result[1] == "ACTIVE"  # Middle splits
        assert result[2] == "ACTIVE"  # Middle splits
        assert result[3] == "COOLDOWN"  # Last split

    @pytest.mark.unit
    def test_estimate_intensity_type_missing_hr_values(self):
        """Test estimation handles missing HR values gracefully."""

        # Test case: Some splits without HR data (6 splits total)
        # With 6 splits (≤6): WARMUP (1), middle (4), COOLDOWN (1)
        splits: list[dict] = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP (position)
            {
                "pace_seconds_per_km": 300,
                "avg_heart_rate": None,
            },  # ACTIVE (no HR, pace not fast)
            {"pace_seconds_per_km": 220, "avg_heart_rate": 175},  # INTERVAL (by pace)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": None,
            },  # ACTIVE (no HR, pace not fast)
            {"pace_seconds_per_km": 260, "avg_heart_rate": 145},  # ACTIVE
            {"pace_seconds_per_km": 300, "avg_heart_rate": None},  # COOLDOWN (position)
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Should not crash and produce reasonable estimates
        assert result[0] == "WARMUP"  # Position-based
        assert result[1] == "ACTIVE"  # No HR, pace not fast enough
        assert result[2] == "INTERVAL"  # Fast pace detected
        assert result[-1] == "COOLDOWN"  # Position-based

    @pytest.mark.unit
    def test_estimate_intensity_type_single_split(self):
        """Test estimation handles edge case of single split."""

        # Test case: Only 1 split (should not be both WARMUP and COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 270, "avg_heart_rate": 150},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Single split: no warmup/cooldown designation
        assert len(result) == 1
        assert result[0] == "ACTIVE"  # Default to ACTIVE

    @pytest.mark.unit
    def test_estimate_intensity_type_empty_splits(self):
        """Test estimation handles empty splits list."""

        splits: list[dict] = []

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result == []

    # ===========================================================================
    # Integration tests for intensity_type estimation with insert_splits()
    # ===========================================================================

    @pytest.mark.integration
    def test_insert_splits_estimates_missing_intensity(
        self, tmp_path, initialized_db_path
    ):
        """Test insert_splits applies estimation when intensity_type is NULL."""

        # Create splits file with NULL intensity_type
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "groundContactTime": 250,
                    "verticalOscillation": 8.5,
                    "verticalRatio": 8.0,
                    "elevationGain": 5,
                    "elevationLoss": 2,
                    "intensityType": None,  # NULL - should be estimated
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "groundContactTime": 240,
                    "verticalOscillation": 8.0,
                    "verticalRatio": 7.5,
                    "elevationGain": 3,
                    "elevationLoss": 4,
                    "intensityType": None,  # NULL - should be estimated
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "groundContactTime": 255,
                    "verticalOscillation": 8.7,
                    "verticalRatio": 8.2,
                    "elevationGain": 2,
                    "elevationLoss": 5,
                    "intensityType": None,  # NULL - should be estimated
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify estimation was applied
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # Expected: WARMUP (position), INTERVAL (fast pace), COOLDOWN (position)
        # Paces: 300, 240, 310 sec/km → avg = 283.3
        # Threshold (×0.9): 255 sec/km → split 1 (240) is INTERVAL
        assert splits[0][1] == "WARMUP"  # First split
        assert splits[1][1] == "INTERVAL"  # Fast pace (240 < 255)
        assert splits[2][1] == "COOLDOWN"  # Last split

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_preserves_existing_intensity(
        self, tmp_path, initialized_db_path
    ):
        """Test insert_splits does NOT overwrite existing intensity_type values."""

        # Create splits file with existing intensity_type values
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "groundContactTime": 250,
                    "verticalOscillation": 8.5,
                    "verticalRatio": 8.0,
                    "elevationGain": 5,
                    "elevationLoss": 2,
                    "intensityType": "ACTIVE",  # Existing value
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "groundContactTime": 240,
                    "verticalOscillation": 8.0,
                    "verticalRatio": 7.5,
                    "elevationGain": 3,
                    "elevationLoss": 4,
                    "intensityType": "ACTIVE",  # Existing value
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "groundContactTime": 255,
                    "verticalOscillation": 8.7,
                    "verticalRatio": 8.2,
                    "elevationGain": 2,
                    "elevationLoss": 5,
                    "intensityType": "ACTIVE",  # Existing value
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify existing values are preserved
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # All should remain ACTIVE (existing values preserved)
        assert splits[0][1] == "ACTIVE"
        assert splits[1][1] == "ACTIVE"
        assert splits[2][1] == "ACTIVE"

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_mixed_null_and_existing(self, tmp_path, initialized_db_path):
        """Test insert_splits handles mix of NULL and existing intensity_type."""

        # Create splits file with mix of NULL and existing values
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "intensityType": None,  # NULL - should estimate WARMUP
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "intensityType": "INTERVAL",  # Existing - preserve
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "intensityType": None,  # NULL - should estimate COOLDOWN
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify estimation applied only to NULL values
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # Expected: WARMUP (estimated), INTERVAL (preserved), COOLDOWN (estimated)
        assert splits[0][1] == "WARMUP"  # Estimated from NULL
        assert splits[1][1] == "INTERVAL"  # Preserved existing
        assert splits[2][1] == "COOLDOWN"  # Estimated from NULL

        conn.close()
