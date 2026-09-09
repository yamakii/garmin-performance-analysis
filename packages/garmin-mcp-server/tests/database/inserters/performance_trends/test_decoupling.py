"""Steady-run decoupling and rep-matched drift."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.performance_trends import (
    _compute_rep_matched_drift,
    _compute_steady_decoupling,
    insert_performance_trends,
)
from garmin_mcp.database.readers.performance import PerformanceReader


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
