"""Representative run paces, CV helper and the fragment-free pace-consistency output."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.performance_trends import (
    _cv,
    _extract_performance_trends_from_raw,
    _representative_run_paces,
    insert_performance_trends,
)
from garmin_mcp.database.readers.performance import PerformanceReader


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
    def test_pace_consistency_representative_drops_fragment(self):
        """Representative CV drops the fragment lap entirely (#852)."""
        paces = [461.6, 450.1, 456.6, 437.9, 415.2]
        distances = [1.0, 1.0, 1.0, 1.0, 0.016]
        run_laps = [
            {"pace": p, "distance_km": d} for p, d in zip(paces, distances, strict=True)
        ]
        pace_consistency = _cv(_representative_run_paces(run_laps))
        assert pace_consistency is not None
        assert abs(pace_consistency - 0.0227) < 0.001


class TestPaceConsistencyNoFullVariant:
    """The fragment-inclusive raw CV is gone from every layer (#972)."""

    @pytest.fixture
    def fragment_run_splits_file(self, tmp_path):
        """Single-phase run: 4 x 1 km laps + an 85 m trailing GPS fragment."""
        # paces (s/km): 445, 451, 459, 457, and 418 for the fragment
        specs = [
            (1000.0, 445.0),
            (1000.0, 451.0),
            (1000.0, 459.0),
            (1000.0, 457.0),
            (85.0, 418.0 * 0.085),  # fragment: 85 m -> pace 418 s/km
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
        raw_splits_data = {"activityId": 24221548903, "lapDTOs": lap_dtos}
        raw_splits_file = tmp_path / "fragment_splits.json"
        with open(raw_splits_file, "w", encoding="utf-8") as f:
            json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)
        return raw_splits_file

    @pytest.mark.unit
    def test_pace_consistency_excludes_fragment_only(self, fragment_run_splits_file):
        """Extraction keeps the representative CV and emits no raw-CV key."""
        result = _extract_performance_trends_from_raw(str(fragment_run_splits_file))

        assert result is not None
        pace_consistency = result["pace_consistency"]
        assert pace_consistency is not None
        # 4 x 1 km laps only (85 m fragment excluded) -> ~1.4%.
        assert abs(pace_consistency - 0.014) < 0.001
        assert "pace_consistency_full" not in result

    @pytest.mark.integration
    def test_get_performance_trends_has_no_full_key(
        self, fragment_run_splits_file, initialized_db_path
    ):
        """The representative CV round-trips; the raw-CV key is absent."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_performance_trends(
            activity_id=24221548903,
            conn=conn,
            raw_splits_file=str(fragment_run_splits_file),
        )
        assert result is True
        conn.close()

        reader = PerformanceReader(db_path=str(db_path))
        trends = reader.get_performance_trends(24221548903)
        assert trends is not None

        pace_consistency = trends["pace_consistency"]
        assert pace_consistency is not None
        assert abs(pace_consistency - 0.014) < 0.001
        assert "pace_consistency_full" not in trends
