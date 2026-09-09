"""Workout-structure classification and the interval / steady branch in get_performance_trends."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.performance_trends import (
    _classify_workout_structure,
    insert_performance_trends,
)
from garmin_mcp.database.readers.performance import PerformanceReader


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
