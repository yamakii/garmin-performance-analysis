"""
Tests for Performance Trends Inserter

Test coverage:
- Unit tests for insert_performance_trends function
- Integration tests with DuckDB
"""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.performance_trends import (
    _classify_workout_structure,
    _compute_rep_matched_drift,
    _compute_steady_decoupling,
    _cv,
    _representative_run_paces,
    insert_performance_trends,
)
from garmin_mcp.database.readers.performance import PerformanceReader


class TestPerformanceTrendsInserter:
    """Test suite for Performance Trends Inserter."""

    @pytest.mark.unit
    def test_insert_performance_trends_success(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_performance_trends inserts data successfully."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_performance_trends_missing_file(self, initialized_db_path):
        """Test insert_performance_trends handles missing file."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=12345,
            conn=conn,
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_performance_trends_no_data(self, tmp_path, initialized_db_path):
        """Test insert_performance_trends handles missing performance_trends."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=12345,
            conn=conn,
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_performance_trends_db_integration(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_performance_trends actually writes to DuckDB."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

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
    def test_insert_4phase_performance_trends(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_performance_trends writes 4-phase interval training data correctly."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Check 4-phase data
        data = conn.execute("""
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
            """).fetchone()

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
    def test_phase_avg_size_weighted_not_plain_mean(
        self, tmp_path, initialized_db_path
    ):
        """A tiny trailing GPS-fragment lap must not distort the phase averages.

        Regression for the phase-average bug: avg_pace/avg_hr were a plain mean
        over splits, so a sub-40 m fragment counted the same as a full 1 km lap.
        Averages must be size-weighted (pace by distance, HR by duration).
        """
        # Run phase: one full 1 km lap + a 40 m fragment with an extreme fast pace.
        raw_splits_data = {
            "activityId": 30303030303,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 480.0,  # pace 480 s/km
                    "intensityType": "ACTIVE",
                    "averageHR": 145,
                    "averageRunCadence": 180.0,
                    "averagePower": 240,
                },
                {
                    "lapIndex": 2,
                    "distance": 40.0,
                    "duration": 15.0,  # pace 375 s/km (noisy fragment)
                    "intensityType": "ACTIVE",
                    "averageHR": 150,
                    "averageRunCadence": 174.0,
                    "averagePower": 270,
                },
            ],
        }
        raw_splits_file = tmp_path / "splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)

        conn = duckdb.connect(str(initialized_db_path))
        assert (
            insert_performance_trends(
                activity_id=30303030303,
                conn=conn,
                raw_splits_file=str(raw_splits_file),
            )
            is True
        )

        data = conn.execute("""
            SELECT run_avg_pace_seconds_per_km, run_avg_hr
            FROM performance_trends
            WHERE activity_id = 30303030303
            """).fetchone()
        conn.close()

        assert data is not None
        # Distance-weighted pace = (480 + 15) / (1.0 + 0.04) = 476.0 s/km,
        # NOT the plain mean (480 + 375) / 2 = 427.5 that the fragment would force.
        assert abs(data[0] - 476.0) < 0.5
        assert abs(data[0] - 427.5) > 40.0
        # Time-weighted HR = (145*480 + 150*15) / 495 = 145.15 -> 145.2,
        # NOT the plain mean (145 + 150) / 2 = 147.5.
        assert abs(data[1] - 145.2) < 0.2

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
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_performance_trends with raw data mode."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_performance_trends_raw_data_db_integration(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test insert_performance_trends with raw data actually writes to DuckDB."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        # Check 4-phase data
        data = conn.execute("""
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
            """).fetchone()

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
    def test_insert_performance_trends_raw_data_missing_file(self, initialized_db_path):
        """Test insert_performance_trends raw mode handles missing files."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=12345,
            conn=conn,
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_warmup_cadence_power_calculation(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test warmup_avg_cadence and warmup_avg_power calculation."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        data = conn.execute("""
            SELECT warmup_avg_cadence, warmup_avg_power
            FROM performance_trends
            WHERE activity_id = 20636804823
            """).fetchone()
        assert data is not None

        # Sample has warmup split with cadence=183.6, power=268
        assert data[0] == 183.6  # warmup_avg_cadence
        assert data[1] == 268.0  # warmup_avg_power
        conn.close()

    @pytest.mark.unit
    def test_warmup_evaluation(self, sample_raw_splits_file, initialized_db_path):
        """Test warmup_evaluation field."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        _row = conn.execute(
            "SELECT warmup_evaluation FROM performance_trends WHERE activity_id = 20636804823"
        ).fetchone()
        assert _row is not None
        evaluation = _row[0]

        # Should have a valid evaluation
        assert evaluation in [
            "Excellent warmup",
            "Good warmup",
            "Minimal warmup",
            "No warmup",
        ]
        conn.close()

    @pytest.mark.unit
    def test_run_cadence_power_calculation(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test run_avg_cadence and run_avg_power calculation."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        data = conn.execute("""
            SELECT run_avg_cadence, run_avg_power
            FROM performance_trends
            WHERE activity_id = 20636804823
            """).fetchone()
        assert data is not None

        # Sample has run splits with cadence=187.0 and 186.2, power=262 and 267
        expected_cadence = (187.0 + 186.2) / 2
        expected_power = (262.0 + 267.0) / 2
        assert abs(data[0] - expected_cadence) < 0.1  # run_avg_cadence
        assert abs(data[1] - expected_power) < 0.1  # run_avg_power
        conn.close()

    @pytest.mark.unit
    def test_run_evaluation(self, sample_raw_splits_file, initialized_db_path):
        """Test run_evaluation field."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        _row = conn.execute(
            "SELECT run_evaluation FROM performance_trends WHERE activity_id = 20636804823"
        ).fetchone()
        assert _row is not None
        evaluation = _row[0]

        # Should have a valid evaluation
        assert evaluation in ["Excellent", "Good", "Fair", "Poor"]
        conn.close()

    @pytest.mark.unit
    def test_recovery_cadence_power_calculation(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test recovery_avg_cadence and recovery_avg_power calculation."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        data = conn.execute("""
            SELECT recovery_avg_cadence, recovery_avg_power
            FROM performance_trends
            WHERE activity_id = 20636804823
            """).fetchone()
        assert data is not None

        # Sample has recovery split with cadence=170.0, power=200
        assert data[0] == 170.0  # recovery_avg_cadence
        assert data[1] == 200.0  # recovery_avg_power
        conn.close()

    @pytest.mark.unit
    def test_recovery_evaluation(self, sample_raw_splits_file, initialized_db_path):
        """Test recovery_evaluation field."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        _row = conn.execute(
            "SELECT recovery_evaluation FROM performance_trends WHERE activity_id = 20636804823"
        ).fetchone()
        assert _row is not None
        evaluation = _row[0]

        # Should have a valid evaluation
        assert evaluation in [
            "Excellent recovery",
            "Good recovery",
            "Insufficient recovery",
            "No recovery",
        ]
        conn.close()

    @pytest.mark.unit
    def test_cooldown_cadence_power_calculation(
        self, sample_raw_splits_file, initialized_db_path
    ):
        """Test cooldown_avg_cadence and cooldown_avg_power calculation."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        data = conn.execute("""
            SELECT cooldown_avg_cadence, cooldown_avg_power
            FROM performance_trends
            WHERE activity_id = 20636804823
            """).fetchone()
        assert data is not None

        # Sample has cooldown split with cadence=175.0, power=220
        assert data[0] == 175.0  # cooldown_avg_cadence
        assert data[1] == 220.0  # cooldown_avg_power
        conn.close()

    @pytest.mark.unit
    def test_cooldown_evaluation(self, sample_raw_splits_file, initialized_db_path):
        """Test cooldown_evaluation field."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=20636804823,
            conn=conn,
            raw_splits_file=str(sample_raw_splits_file),
        )

        assert result is True

        conn = duckdb.connect(str(db_path))
        _row = conn.execute(
            "SELECT cooldown_evaluation FROM performance_trends WHERE activity_id = 20636804823"
        ).fetchone()
        assert _row is not None
        evaluation = _row[0]

        # Should have a valid evaluation
        assert evaluation in [
            "Excellent cooldown",
            "Good cooldown",
            "Minimal cooldown",
            "No cooldown",
        ]
        conn.close()


class TestSteadyDecoupling:
    """Unit tests for _compute_steady_decoupling (Pa:HR decoupling)."""

    @pytest.mark.unit
    def test_decoupling_single_phase_easy_run_not_null(self):
        """Single-phase easy run (no warmup/cooldown) returns positive float."""
        # 8 run laps, constant pace, second half HR +5bpm
        run_splits = [
            {"lap_index": i, "pace": 360.0, "hr": 145 if i < 4 else 150}
            for i in range(8)
        ]
        result = _compute_steady_decoupling(run_splits)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

    @pytest.mark.unit
    def test_decoupling_well_coupled_under_5pct(self):
        """~3% efficiency-ratio difference returns < 5.0."""
        # Constant pace, HR 100 -> 103: decoupling ~= (3/103)*100 = 2.9%
        run_splits = [
            {"lap_index": i, "pace": 360.0, "hr": 100 if i < 4 else 103}
            for i in range(8)
        ]
        result = _compute_steady_decoupling(run_splits)
        assert result is not None
        assert 0 < result < 5.0

    @pytest.mark.unit
    def test_decoupling_high_drift_positive(self):
        """Large second-half HR rise at same pace returns > 5.0 positive."""
        # Constant pace, HR 140 -> 165: decoupling ~= (25/165)*100 = 15.2%
        run_splits = [
            {"lap_index": i, "pace": 360.0, "hr": 140 if i < 4 else 165}
            for i in range(8)
        ]
        result = _compute_steady_decoupling(run_splits)
        assert result is not None
        assert result > 5.0

    @pytest.mark.unit
    def test_decoupling_insufficient_laps_returns_none(self):
        """A single usable lap cannot be split -> None."""
        run_splits = [{"lap_index": 0, "pace": 360.0, "hr": 145}]
        assert _compute_steady_decoupling(run_splits) is None

    @pytest.mark.unit
    def test_decoupling_missing_hr_returns_none(self):
        """All laps missing HR -> None."""
        run_splits = [{"lap_index": i, "pace": 360.0, "hr": None} for i in range(8)]
        assert _compute_steady_decoupling(run_splits) is None


class TestEasyRunDecouplingIntegration:
    """Integration: single-phase easy run yields non-null hr_drift_percentage."""

    @pytest.fixture
    def easy_run_splits_file(self, tmp_path):
        """Single-phase easy run (all ACTIVE laps, no warmup/cooldown)."""
        raw_splits_data = {
            "activityId": 99887766,
            "lapDTOs": [
                {
                    "lapIndex": i + 1,
                    "distance": 1000.0,
                    "duration": 360.0,
                    "intensityType": "ACTIVE",
                    "averageHR": 138 if i < 3 else 144,
                    "averageRunCadence": 180.0,
                    "averagePower": 250,
                }
                for i in range(6)
            ],
        }
        raw_splits_file = tmp_path / "easy_run_splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)
        return raw_splits_file

    @pytest.mark.integration
    def test_get_performance_trends_easy_run_has_drift(
        self, easy_run_splits_file, initialized_db_path
    ):
        """Ingest single run-phase easy run -> get_performance_trends drift is float."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=99887766,
            conn=conn,
            raw_splits_file=str(easy_run_splits_file),
        )
        assert result is True
        conn.close()

        reader = PerformanceReader(db_path=str(db_path))
        trends = reader.get_performance_trends(99887766)

        assert trends is not None
        drift = trends["hr_drift_percentage"]
        assert drift is not None
        assert isinstance(drift, float)


class TestWorkoutStructureClassification:
    """Unit tests for _classify_workout_structure."""

    @pytest.mark.unit
    def test_classify_steady_single_intensity(self):
        """All laps ACTIVE (no rest segments) -> 'steady'."""
        lap_dtos = [{"lapIndex": i + 1, "intensityType": "ACTIVE"} for i in range(8)]
        assert _classify_workout_structure(lap_dtos) == "steady"

    @pytest.mark.unit
    def test_classify_interval_alternating(self):
        """ACTIVE/REST alternating 5 times -> 'interval'."""
        lap_dtos = []
        for i in range(5):
            lap_dtos.append({"lapIndex": 2 * i + 1, "intensityType": "ACTIVE"})
            lap_dtos.append({"lapIndex": 2 * i + 2, "intensityType": "REST"})
        assert _classify_workout_structure(lap_dtos) == "interval"

    @pytest.mark.unit
    def test_classify_unknown_falls_back_steady(self):
        """Missing intensityType (no classification material) -> 'steady'."""
        lap_dtos = [{"lapIndex": i + 1} for i in range(6)]
        assert _classify_workout_structure(lap_dtos) == "steady"


class TestRepMatchedDrift:
    """Unit tests for _compute_rep_matched_drift."""

    @pytest.mark.unit
    def test_rep_drift_late_reps_higher_hr(self):
        """5 reps at same pace with rising HR (145->152) -> positive %."""
        active_reps = [
            {"lap_index": i, "pace": 360.0, "hr": 145 + i * 1.75} for i in range(5)
        ]
        result = _compute_rep_matched_drift(active_reps)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

    @pytest.mark.unit
    def test_rep_drift_single_rep_returns_none(self):
        """A single ACTIVE rep cannot be split -> None."""
        active_reps = [{"lap_index": 0, "pace": 360.0, "hr": 150}]
        assert _compute_rep_matched_drift(active_reps) is None

    @pytest.mark.unit
    def test_rep_drift_missing_hr_returns_none(self):
        """All reps missing HR -> None."""
        active_reps = [{"lap_index": i, "pace": 360.0, "hr": None} for i in range(5)]
        assert _compute_rep_matched_drift(active_reps) is None


class TestWorkoutStructureBranchIntegration:
    """Integration: hr_drift_percentage routes through the correct branch."""

    @pytest.fixture
    def interval_splits_file(self, tmp_path):
        """Interval session: 5 ACTIVE reps alternating with REST, rising HR."""
        lap_dtos = []
        for i in range(5):
            lap_dtos.append(
                {
                    "lapIndex": 2 * i + 1,
                    "distance": 1000.0,
                    "duration": 360.0,
                    "intensityType": "ACTIVE",
                    "averageHR": 150 + i * 2,  # 150,152,154,156,158
                    "averageRunCadence": 185.0,
                    "averagePower": 280,
                }
            )
            lap_dtos.append(
                {
                    "lapIndex": 2 * i + 2,
                    "distance": 200.0,
                    "duration": 120.0,
                    "intensityType": "REST",
                    "averageHR": 120,
                    "averageRunCadence": 160.0,
                    "averagePower": 150,
                }
            )
        raw_splits_data = {"activityId": 55443322, "lapDTOs": lap_dtos}
        raw_splits_file = tmp_path / "interval_splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)
        return raw_splits_file

    @pytest.fixture
    def steady_run_splits_file(self, tmp_path):
        """Steady easy run: all ACTIVE laps, second half HR slightly higher."""
        raw_splits_data = {
            "activityId": 66554433,
            "lapDTOs": [
                {
                    "lapIndex": i + 1,
                    "distance": 1000.0,
                    "duration": 360.0,
                    "intensityType": "ACTIVE",
                    "averageHR": 140 if i < 4 else 146,
                    "averageRunCadence": 180.0,
                    "averagePower": 250,
                }
                for i in range(8)
            ],
        }
        raw_splits_file = tmp_path / "steady_run_splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)
        return raw_splits_file

    @pytest.mark.integration
    def test_interval_session_uses_rep_matched_drift(
        self, interval_splits_file, initialized_db_path
    ):
        """Interval activity -> hr_drift_percentage non-null via rep-matched path."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=55443322,
            conn=conn,
            raw_splits_file=str(interval_splits_file),
        )
        assert result is True
        conn.close()

        reader = PerformanceReader(db_path=str(db_path))
        trends = reader.get_performance_trends(55443322)
        assert trends is not None

        drift = trends["hr_drift_percentage"]
        assert drift is not None
        assert isinstance(drift, float)
        # Late reps have higher HR at the same pace -> positive drift.
        assert drift > 0

    @pytest.mark.integration
    def test_steady_run_still_uses_decoupling(
        self, steady_run_splits_file, initialized_db_path
    ):
        """Steady easy run -> #sub-1 steady decoupling path stays non-null."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=66554433,
            conn=conn,
            raw_splits_file=str(steady_run_splits_file),
        )
        assert result is True
        conn.close()

        reader = PerformanceReader(db_path=str(db_path))
        trends = reader.get_performance_trends(66554433)
        assert trends is not None

        drift = trends["hr_drift_percentage"]
        assert drift is not None
        assert isinstance(drift, float)


class TestRepresentativeRunPacesAndCV:
    """Unit tests for representative-lap CV helpers (#852)."""

    @pytest.mark.unit
    def test_representative_run_paces_excludes_short_fragment(self):
        """A 16 m GPS-fragment lap is excluded; the 4 full laps remain."""
        paces = [461.6, 450.1, 456.6, 437.9, 415.2]
        distances = [1.0, 1.0, 1.0, 1.0, 0.016]
        run_laps = [
            {"pace": p, "distance_km": d} for p, d in zip(paces, distances, strict=True)
        ]
        assert _representative_run_paces(run_laps) == [461.6, 450.1, 456.6, 437.9]

    @pytest.mark.unit
    def test_representative_run_paces_all_full_distance_unchanged(self):
        """Uniform 1 km laps all pass the median filter (behavior unchanged)."""
        paces = [400.0, 410.0, 405.0, 398.0]
        run_laps = [{"pace": p, "distance_km": 1.0} for p in paces]
        assert _representative_run_paces(run_laps) == paces

    @pytest.mark.unit
    def test_representative_run_paces_fallback_under_two(self):
        """Filter leaving <2 laps falls back to all paces."""
        run_laps = [
            {"pace": 400.0, "distance_km": 1.0},
            {"pace": 900.0, "distance_km": 0.01},
        ]
        assert _representative_run_paces(run_laps) == [400.0, 900.0]

    @pytest.mark.unit
    def test_cv_helper(self):
        """CV = stdev/mean; single value -> 0.0; empty -> None."""
        cv_two = _cv([400.0, 500.0])
        assert cv_two is not None
        assert abs(cv_two - 0.157135) < 0.001
        assert _cv([440.0]) == 0.0
        assert _cv([]) is None

    @pytest.mark.unit
    def test_pace_consistency_representative_vs_full(self):
        """Representative CV drops the fragment; full CV keeps it (#852)."""
        paces = [461.6, 450.1, 456.6, 437.9, 415.2]
        distances = [1.0, 1.0, 1.0, 1.0, 0.016]
        run_laps = [
            {"pace": p, "distance_km": d} for p, d in zip(paces, distances, strict=True)
        ]
        pace_consistency = _cv(_representative_run_paces(run_laps))
        pace_consistency_full = _cv(paces)
        assert pace_consistency is not None
        assert pace_consistency_full is not None
        assert abs(pace_consistency - 0.0227) < 0.001
        assert abs(pace_consistency_full - 0.0417) < 0.001


class TestPaceConsistencyFullPersistence:
    """Integration: pace_consistency_full is persisted and read back (#852)."""

    @pytest.fixture
    def fragment_run_splits_file(self, tmp_path):
        """Single-phase run: 4 full laps + a 16 m trailing GPS fragment."""
        # paces (s/km): 461.6, 450.1, 456.6, 437.9, 415.2
        specs = [
            (1000.0, 461.6),
            (1000.0, 450.1),
            (1000.0, 456.6),
            (1000.0, 437.9),
            (16.0, 415.2 * 0.016),  # fragment: 16 m -> pace 415.2 s/km
        ]
        lap_dtos = [
            {
                "lapIndex": i + 1,
                "distance": dist,
                "duration": dur,
                "intensityType": "ACTIVE",
                "averageHR": 150,
                "averageRunCadence": 180.0,
                "averagePower": 250,
            }
            for i, (dist, dur) in enumerate(specs)
        ]
        raw_splits_data = {"activityId": 23554970343, "lapDTOs": lap_dtos}
        raw_splits_file = tmp_path / "fragment_splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)
        return raw_splits_file

    @pytest.mark.integration
    def test_pace_consistency_full_persisted_and_read(
        self, fragment_run_splits_file, initialized_db_path
    ):
        """insert_performance_trends persists both CVs; reader returns both."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=23554970343,
            conn=conn,
            raw_splits_file=str(fragment_run_splits_file),
        )
        assert result is True
        conn.close()

        reader = PerformanceReader(db_path=str(db_path))
        trends = reader.get_performance_trends(23554970343)
        assert trends is not None

        pace_consistency = trends["pace_consistency"]
        pace_consistency_full = trends["pace_consistency_full"]
        assert pace_consistency is not None
        assert pace_consistency_full is not None
        # Representative CV excludes the 16 m fragment -> ~2.27%.
        assert abs(pace_consistency - 0.0227) < 0.001
        # Full CV includes the fragment -> ~4.17%.
        assert abs(pace_consistency_full - 0.0417) < 0.001
