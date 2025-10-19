"""
Tests for TimeSeriesMetrics Inserter

Test coverage:
- Unit tests for insert_time_series_metrics function
- Metric name conversion (directHeartRate -> heart_rate)
- Unit conversion (speed × 0.1, elevation ÷ 100.0)
- Timestamp calculation (sumDuration / 1000.0)
- Batch insert performance
- Duplicate handling
"""

import json

import duckdb
import pytest

from tools.database.inserters.time_series_metrics import insert_time_series_metrics


class TestTimeSeriesMetricsInserter:
    """Test suite for TimeSeriesMetrics Inserter."""

    @pytest.fixture
    def sample_activity_details_file(self, tmp_path):
        """Create sample activity_details.json file with time series data."""
        activity_details_data = {
            "activityId": 20636804823,
            "measurementCount": 5,  # Simplified: only 5 metrics
            "metricsCount": 3,  # 3 time points
            "metricDescriptors": [
                {
                    "metricsIndex": 0,
                    "key": "sumDuration",
                    "unit": {"id": 40, "key": "second", "factor": 1000.0},
                },
                {
                    "metricsIndex": 1,
                    "key": "directHeartRate",
                    "unit": {"id": 3, "key": "bpm", "factor": 1.0},
                },
                {
                    "metricsIndex": 2,
                    "key": "directSpeed",
                    "unit": {"id": 20, "key": "mps", "factor": 0.1},
                },
                {
                    "metricsIndex": 3,
                    "key": "directElevation",
                    "unit": {"id": 1, "key": "meter", "factor": 100.0},
                },
                {
                    "metricsIndex": 4,
                    "key": "directRunCadence",
                    "unit": {"id": 92, "key": "stepsPerMinute", "factor": 1.0},
                },
            ],
            "activityDetailMetrics": [
                {
                    "metrics": [
                        1,  # sumDuration = 1s (API sends seconds despite factor=1000)
                        140,  # heart_rate = 140 bpm
                        30,  # speed = 30 × 0.1 = 3.0 m/s
                        50000,  # elevation = 50000 / 100.0 = 500.0 m
                        170,  # cadence = 170 spm
                    ]
                },
                {
                    "metrics": [
                        2,  # sumDuration = 2s (API sends seconds despite factor=1000)
                        145,  # heart_rate = 145 bpm
                        32,  # speed = 32 × 0.1 = 3.2 m/s
                        50100,  # elevation = 50100 / 100.0 = 501.0 m
                        172,  # cadence = 172 spm
                    ]
                },
                {
                    "metrics": [
                        3,  # sumDuration = 3s (API sends seconds despite factor=1000)
                        150,  # heart_rate = 150 bpm
                        None,  # speed = None (missing data)
                        50200,  # elevation = 50200 / 100.0 = 502.0 m
                        175,  # cadence = 175 spm
                    ]
                },
            ],
        }

        activity_details_file = tmp_path / "activity_details.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f, ensure_ascii=False, indent=2)

        return activity_details_file

    @pytest.mark.unit
    def test_insert_time_series_metrics_success(
        self, sample_activity_details_file, tmp_path
    ):
        """Test insert_time_series_metrics inserts data successfully."""
        # Setup: Create temporary DuckDB
        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        # Verify
        assert result is True
        assert db_path.exists()

        # Verify data was inserted
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT * FROM time_series_metrics WHERE activity_id = ? ORDER BY timestamp_s",
            [20636804823],
        ).fetchall()
        conn.close()

        assert len(rows) == 3  # 3 time points

    @pytest.mark.unit
    def test_metric_name_conversion(self, sample_activity_details_file, tmp_path):
        """Test metric name conversion: directHeartRate -> heart_rate."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify column names are normalized
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT heart_rate, speed, cadence FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 140.0  # heart_rate
        assert row[1] == 30.0  # speed (raw value, no conversion)
        assert row[2] == 170.0  # cadence

    @pytest.mark.unit
    def test_unit_conversion_speed(self, sample_activity_details_file, tmp_path):
        """Test that speed raw value is used as-is (no factor conversion)."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify speed is raw value
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT speed FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        # Raw value: 30 (already in m/s, no factor conversion needed)
        assert row is not None
        assert row[0] == 30.0

    @pytest.mark.unit
    def test_unit_conversion_elevation(self, sample_activity_details_file, tmp_path):
        """Test that elevation raw value is used as-is (no factor conversion)."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify elevation is raw value
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT elevation FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        # Raw value: 50000 (already in meters, no factor conversion needed)
        assert row is not None
        assert row[0] == 50000.0

    @pytest.mark.unit
    def test_timestamp_calculation(self, sample_activity_details_file, tmp_path):
        """Test timestamp_s calculation from sumDuration (already in seconds)."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify timestamp_s values
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT timestamp_s FROM time_series_metrics WHERE activity_id = ? ORDER BY timestamp_s",
            [20636804823],
        ).fetchall()
        conn.close()

        # sumDuration: [1, 2, 3] → timestamp_s: [1, 2, 3]
        assert rows[0][0] == 1
        assert rows[1][0] == 2
        assert rows[2][0] == 3

    @pytest.mark.unit
    def test_null_handling(self, sample_activity_details_file, tmp_path):
        """Test NULL handling for missing metrics."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify NULL for missing speed at timestamp_s=3
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT speed FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 3],
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] is None  # Speed is NULL

    @pytest.mark.unit
    def test_duplicate_handling(self, sample_activity_details_file, tmp_path):
        """Test duplicate handling: DELETE before INSERT."""
        db_path = tmp_path / "test.duckdb"

        # First insertion
        result1 = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )
        assert result1 is True

        # Second insertion (should replace)
        result2 = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )
        assert result2 is True

        # Verify still only 3 rows (not 6)
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?",
            [20636804823],
        ).fetchone()
        conn.close()

        assert rows is not None
        assert rows[0] == 3

    @pytest.mark.unit
    def test_insert_missing_file(self, tmp_path):
        """Test insert_time_series_metrics handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_invalid_json(self, tmp_path):
        """Test insert_time_series_metrics handles invalid JSON."""
        # Create invalid JSON file
        invalid_file = tmp_path / "invalid.json"
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(invalid_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_no_metric_descriptors(self, tmp_path):
        """Test insert_time_series_metrics handles missing metricDescriptors."""
        # Create activity_details.json without metricDescriptors
        activity_details_data = {
            "activityId": 12345,
            "activityDetailMetrics": [{"metrics": [1000, 140]}],
        }

        activity_details_file = tmp_path / "activity_details.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.performance
    @pytest.mark.slow
    def test_batch_insert_performance(self, tmp_path):
        """Test batch insert performance: 2000 rows in reasonable time (<5s)."""
        import time

        # Create large dataset (2000 time points)
        activity_details_data = {
            "activityId": 99999,
            "measurementCount": 3,
            "metricsCount": 2000,
            "metricDescriptors": [
                {
                    "metricsIndex": 0,
                    "key": "sumDuration",
                    "unit": {"id": 40, "key": "second", "factor": 1000.0},
                },
                {
                    "metricsIndex": 1,
                    "key": "directHeartRate",
                    "unit": {"id": 3, "key": "bpm", "factor": 1.0},
                },
                {
                    "metricsIndex": 2,
                    "key": "directSpeed",
                    "unit": {"id": 20, "key": "mps", "factor": 0.1},
                },
            ],
            "activityDetailMetrics": [
                {"metrics": [i, 140 + (i % 20), 30 + (i % 5)]} for i in range(1, 2001)
            ],
        }

        activity_details_file = tmp_path / "large_activity_details.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f)

        db_path = tmp_path / "test.duckdb"

        # Measure insertion time
        start_time = time.time()
        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=99999,
            db_path=str(db_path),
        )
        elapsed_time = time.time() - start_time

        assert result is True
        # Note: Table creation + indexing adds overhead. 5s is acceptable for 2000 rows.
        assert (
            elapsed_time < 5.0
        ), f"Insertion took {elapsed_time:.2f}s (expected < 5.0s)"

        # Verify row count
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?", [99999]
        ).fetchone()
        conn.close()

        assert rows is not None
        assert rows[0] == 2000

    @pytest.mark.unit
    def test_timestamp_s_uniqueness_with_seq_no(self, tmp_path):
        """Test seq_no prevents PRIMARY KEY violation when timestamp_s duplicates.

        Scenario: Multiple data points within same second (sub-second sampling).
        - sumDuration: 0s (multiple samples) → timestamp_s=0
        - sumDuration: 1s (multiple samples) → timestamp_s=1

        Without seq_no: PRIMARY KEY (activity_id, timestamp_s) would fail.
        With seq_no: PRIMARY KEY (activity_id, seq_no) succeeds.
        """
        # Create dataset with duplicate timestamp_s (realistic scenario)
        activity_details_data = {
            "activityId": 88888,
            "measurementCount": 2,
            "metricsCount": 6,
            "metricDescriptors": [
                {
                    "metricsIndex": 0,
                    "key": "sumDuration",
                    "unit": {"id": 40, "key": "second", "factor": 1000.0},
                },
                {
                    "metricsIndex": 1,
                    "key": "directHeartRate",
                    "unit": {"id": 3, "key": "bpm", "factor": 1.0},
                },
            ],
            "activityDetailMetrics": [
                {"metrics": [0, 140]},  # timestamp_s=0, seq_no=0
                {"metrics": [0, 142]},  # timestamp_s=0, seq_no=1
                {"metrics": [0, 145]},  # timestamp_s=0, seq_no=2
                {"metrics": [1, 148]},  # timestamp_s=1, seq_no=3
                {"metrics": [1, 150]},  # timestamp_s=1, seq_no=4
                {"metrics": [1, 152]},  # timestamp_s=1, seq_no=5
            ],
        }

        activity_details_file = tmp_path / "duplicate_ts.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f)

        db_path = tmp_path / "test.duckdb"

        # Execute insertion
        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=88888,
            db_path=str(db_path),
        )

        # Verify insertion succeeded
        assert result is True

        # Verify all 6 rows inserted (not just 2 unique timestamp_s)
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?",
            [88888],
        ).fetchone()
        assert rows is not None
        assert rows[0] == 6, "All 6 data points should be inserted"

        # Verify seq_no column exists and is sequential
        seq_rows = conn.execute(
            "SELECT seq_no, timestamp_s FROM time_series_metrics WHERE activity_id = ? ORDER BY seq_no",
            [88888],
        ).fetchall()
        conn.close()

        # Verify seq_no is 0-indexed and sequential
        assert seq_rows[0] == (0, 0)  # seq_no=0, timestamp_s=0
        assert seq_rows[1] == (1, 0)  # seq_no=1, timestamp_s=0
        assert seq_rows[2] == (2, 0)  # seq_no=2, timestamp_s=0
        assert seq_rows[3] == (3, 1)  # seq_no=3, timestamp_s=1
        assert seq_rows[4] == (4, 1)  # seq_no=4, timestamp_s=1
        assert seq_rows[5] == (5, 1)  # seq_no=5, timestamp_s=1

    @pytest.mark.unit
    def test_cadence_columns_exist(self, sample_activity_details_file, tmp_path):
        """Test new cadence columns exist in schema (cadence_single_foot, cadence_total).

        Verifies schema migration includes:
        - cadence: DEPRECATED (backward compatibility)
        - cadence_single_foot: Raw single-foot cadence from API
        - cadence_total: Calculated total cadence (both feet)
        """
        db_path = tmp_path / "test.duckdb"

        # Insert to create table
        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Verify schema includes new columns
        conn = duckdb.connect(str(db_path), read_only=True)
        schema = conn.execute("PRAGMA table_info(time_series_metrics)").fetchall()
        conn.close()

        column_names = [row[1] for row in schema]

        # Old column (backward compat)
        assert "cadence" in column_names, "Old cadence column should exist"

        # New columns
        assert (
            "cadence_single_foot" in column_names
        ), "cadence_single_foot column should exist"
        assert "cadence_total" in column_names, "cadence_total column should exist"

        # Verify column types are DOUBLE
        column_types = {row[1]: row[2] for row in schema}
        assert column_types["cadence"] == "DOUBLE"
        assert column_types["cadence_single_foot"] == "DOUBLE"
        assert column_types["cadence_total"] == "DOUBLE"

    @pytest.mark.unit
    def test_cadence_single_foot_extraction(
        self, sample_activity_details_file, tmp_path
    ):
        """Test cadence_single_foot stores raw API value (e.g., 90 spm).

        Garmin API directRunCadence provides single-foot cadence.
        Test data: 170 spm (single-foot)
        """
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Query cadence_single_foot
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT cadence_single_foot FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        assert row is not None
        # Test data has directRunCadence = 170 (single-foot)
        assert row[0] == 170.0, "cadence_single_foot should match raw API value"

    @pytest.mark.unit
    def test_cadence_total_calculation(self, sample_activity_details_file, tmp_path):
        """Test cadence_total calculates both-feet cadence (cadence_single_foot × 2).

        Expected: cadence_total = cadence_single_foot × 2
        Test data: 170 spm (single-foot) → 340 spm (total)
        """
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Query both cadence columns
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT cadence_single_foot, cadence_total FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        assert row is not None
        cadence_single_foot, cadence_total = row

        # Verify calculation
        assert cadence_single_foot == 170.0
        assert cadence_total == 340.0, "cadence_total should be cadence_single_foot × 2"

    @pytest.mark.unit
    def test_cadence_null_handling(self, tmp_path):
        """Test NULL handling when cadence data missing.

        If cadence_single_foot is None, cadence_total should also be None.
        """
        # Create activity_details.json with missing cadence data
        activity_details_data = {
            "activityId": 77777,
            "measurementCount": 2,
            "metricsCount": 1,
            "metricDescriptors": [
                {
                    "metricsIndex": 0,
                    "key": "sumDuration",
                    "unit": {"id": 40, "key": "second", "factor": 1000.0},
                },
                {
                    "metricsIndex": 1,
                    "key": "directHeartRate",
                    "unit": {"id": 3, "key": "bpm", "factor": 1.0},
                },
                # Note: directRunCadence intentionally missing
            ],
            "activityDetailMetrics": [
                {"metrics": [1, 140]},  # No cadence data
            ],
        }

        activity_details_file = tmp_path / "no_cadence.json"
        with open(activity_details_file, "w", encoding="utf-8") as f:
            json.dump(activity_details_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=77777,
            db_path=str(db_path),
        )

        assert result is True

        # Verify both cadence columns are NULL
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT cadence, cadence_single_foot, cadence_total FROM time_series_metrics WHERE activity_id = ?",
            [77777],
        ).fetchone()
        conn.close()

        assert row is not None
        cadence, cadence_single_foot, cadence_total = row
        assert cadence is None, "Old cadence column should be NULL when missing"
        assert (
            cadence_single_foot is None
        ), "cadence_single_foot should be NULL when missing"
        assert cadence_total is None, "cadence_total should be NULL when missing"

    @pytest.mark.unit
    def test_cadence_backward_compatibility(
        self, sample_activity_details_file, tmp_path
    ):
        """Test backward compatibility: old cadence column still works.

        Old queries using 'cadence' column should continue to work.
        The old column should contain the same value as cadence_single_foot.
        """
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Query old cadence column
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute(
            "SELECT cadence, cadence_single_foot FROM time_series_metrics WHERE activity_id = ? AND timestamp_s = ?",
            [20636804823, 1],
        ).fetchone()
        conn.close()

        assert row is not None
        old_cadence, new_single_foot = row

        # Old column should match single-foot value (backward compat)
        assert (
            old_cadence == new_single_foot
        ), "Old cadence column should equal cadence_single_foot for backward compatibility"
        assert old_cadence == 170.0

    @pytest.mark.unit
    def test_cadence_calculation_all_rows(self, sample_activity_details_file, tmp_path):
        """Test cadence_total calculation across all time points.

        Verifies calculation is consistent for all rows in dataset.
        Test data has 3 time points with different cadence values.
        """
        db_path = tmp_path / "test.duckdb"

        result = insert_time_series_metrics(
            activity_details_file=str(sample_activity_details_file),
            activity_id=20636804823,
            db_path=str(db_path),
        )

        assert result is True

        # Query all rows
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT timestamp_s, cadence_single_foot, cadence_total FROM time_series_metrics WHERE activity_id = ? ORDER BY timestamp_s",
            [20636804823],
        ).fetchall()
        conn.close()

        assert len(rows) == 3

        # Verify calculation for each row
        # Test data: cadence values are [170, 172, 175]
        expected_values = [
            (1, 170.0, 340.0),
            (2, 172.0, 344.0),
            (3, 175.0, 350.0),
        ]

        for row, expected in zip(rows, expected_values, strict=True):
            timestamp_s, cadence_single_foot, cadence_total = row
            exp_ts, exp_single, exp_total = expected

            assert timestamp_s == exp_ts
            assert cadence_single_foot == exp_single
            assert cadence_total == exp_total
            assert (
                cadence_total == cadence_single_foot * 2
            ), f"Row {timestamp_s}: cadence_total should be cadence_single_foot × 2"
