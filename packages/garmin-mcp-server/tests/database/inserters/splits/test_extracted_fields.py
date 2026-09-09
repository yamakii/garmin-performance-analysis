"""extract_splits(): stride / max / power / speed metrics, new columns, partial fields, real activity data, population rates."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.splits import insert_splits
from garmin_mcp.database.inserters.splits_helpers.extractor import SplitsExtractor


class TestExtractedFields:
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
