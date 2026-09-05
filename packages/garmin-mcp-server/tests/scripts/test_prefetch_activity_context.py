"""Tests for prefetch_activity_context module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.scripts.prefetch_activity_context import (
    _build_phase_dict,
    _classify_terrain,
    prefetch_activity_context,
)


@pytest.mark.unit
class TestClassifyTerrain:
    """Test terrain classification logic."""

    def test_none_returns_unknown(self) -> None:
        assert _classify_terrain(None) == "unknown"

    def test_flat(self) -> None:
        assert _classify_terrain(5.0) == "flat"

    def test_undulating(self) -> None:
        assert _classify_terrain(15.0) == "undulating"

    def test_hilly(self) -> None:
        assert _classify_terrain(35.0) == "hilly"

    def test_mountainous(self) -> None:
        assert _classify_terrain(55.0) == "mountainous"

    def test_boundary_flat_undulating(self) -> None:
        assert _classify_terrain(10.0) == "undulating"

    def test_boundary_undulating_hilly(self) -> None:
        assert _classify_terrain(30.0) == "hilly"

    def test_boundary_hilly_mountainous(self) -> None:
        assert _classify_terrain(50.0) == "mountainous"

    def test_classify_terrain_flat_no_undulation(self) -> None:
        # avg in flat band, no significant single-split bump -> stays flat
        assert _classify_terrain(4.0, max_split_change=3.0) == "flat"

    def test_classify_terrain_promoted_to_undulating_by_split(self) -> None:
        # avg in flat band but a single split has gain+loss=19 (>=15)
        # -> promoted to undulating (2026-06-22 regression, Issue #473)
        assert _classify_terrain(4.0, max_split_change=19.0) == "undulating"

    def test_classify_terrain_undulating_by_avg(self) -> None:
        # average-driven undulating; no split data provided
        assert _classify_terrain(15.0, max_split_change=None) == "undulating"

    def test_classify_terrain_hilly_unchanged(self) -> None:
        # hilly stays average-driven regardless of single-split bumps
        assert _classify_terrain(35.0) == "hilly"

    def test_classify_terrain_none(self) -> None:
        assert _classify_terrain(None) == "unknown"


@pytest.mark.unit
class TestBuildPhaseDict:
    """Test phase structure building from query row."""

    def test_3_phase_structure(self) -> None:
        """Standard 3-phase run: warmup, run, cooldown."""
        row = (
            0.017,  # pace_consistency
            2.5,  # hr_drift_percentage
            "stable",  # cadence_consistency
            "none",  # fatigue_pattern
            "6:33/km",  # warmup_avg_pace_str
            134.0,  # warmup_avg_hr
            "1,2",  # warmup_splits
            "5:45/km",  # run_avg_pace_str
            155.0,  # run_avg_hr
            "3,4,5",  # run_splits
            None,  # recovery_avg_pace_str
            None,  # recovery_avg_hr
            None,  # recovery_splits
            "7:12/km",  # cooldown_avg_pace_str
            140.0,  # cooldown_avg_hr
            "6,7",  # cooldown_splits
        )
        result = _build_phase_dict(row, has_recovery=False)

        assert result["pace_consistency"] == 0.017
        assert result["hr_drift_percentage"] == 2.5
        assert result["cadence_consistency"] == "stable"
        assert result["fatigue_pattern"] == "none"
        assert result["warmup"] == {"avg_pace": "6:33/km", "avg_hr": 134.0}
        assert result["run"] == {"avg_pace": "5:45/km", "avg_hr": 155.0}
        assert "recovery" not in result
        assert result["cooldown"] == {"avg_pace": "7:12/km", "avg_hr": 140.0}

    def test_4_phase_structure_with_recovery(self) -> None:
        """4-phase interval: warmup, run, recovery, cooldown."""
        row = (
            0.016,  # pace_consistency
            5.0,  # hr_drift_percentage
            "variable",  # cadence_consistency
            "mild",  # fatigue_pattern
            "6:33/km",  # warmup
            134.0,
            "1,2",
            "4:43/km",  # run
            153.0,
            "3,4,5",
            "11:07/km",  # recovery
            150.0,
            "r1,r2",
            "9:27/km",  # cooldown
            135.0,
            "6,7,8",
        )
        result = _build_phase_dict(row, has_recovery=True)

        assert "recovery" in result
        assert result["recovery"] == {"avg_pace": "11:07/km", "avg_hr": 150.0}

    def test_no_warmup_phase(self) -> None:
        """Run without warmup (warmup_splits is None)."""
        row = (
            0.02,
            3.0,
            "stable",
            "none",
            None,  # warmup_avg_pace_str
            None,  # warmup_avg_hr
            None,  # warmup_splits (null)
            "5:45/km",
            155.0,
            "1,2,3",
            None,
            None,
            None,
            None,
            None,
            None,
        )
        result = _build_phase_dict(row, has_recovery=False)

        assert "warmup" not in result
        assert "run" in result
        assert "cooldown" not in result

    def test_build_phase_dict_omits_full(self) -> None:
        """The fragment-inclusive raw CV key is gone from the bundle (#972)."""
        row = (
            0.017,  # pace_consistency
            2.5,  # hr_drift_percentage
            "stable",  # cadence_consistency
            "none",  # fatigue_pattern
            "6:33/km",  # warmup_avg_pace_str
            134.0,  # warmup_avg_hr
            "1,2",  # warmup_splits
            "5:45/km",  # run_avg_pace_str
            155.0,  # run_avg_hr
            "3,4,5",  # run_splits
            None,  # recovery_avg_pace_str
            None,  # recovery_avg_hr
            None,  # recovery_splits
            "7:12/km",  # cooldown_avg_pace_str
            140.0,  # cooldown_avg_hr
            "6,7",  # cooldown_splits
        )
        result = _build_phase_dict(row, has_recovery=False)

        assert set(result) == {
            "pace_consistency",
            "hr_drift_percentage",
            "cadence_consistency",
            "fatigue_pattern",
            "warmup",
            "run",
            "cooldown",
        }
        assert "pace_consistency_full" not in result


@pytest.mark.unit
class TestPrefetchActivityContext:
    """Test the main prefetch function with mocked DB."""

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create a mock DB connection."""
        return MagicMock()

    def _setup_basic_queries(
        self, mock_conn: MagicMock, distance_km: float = 8.2
    ) -> None:
        """Set up mock return values for all 5 queries."""
        import datetime

        mock_conn.execute.return_value.fetchone.side_effect = [
            # Query 1: activity metadata
            # (date, temp, humidity, wind, direction, avg_hr,
            #  avg_pace_s_per_km, total_distance_km, total_time_seconds)
            (
                datetime.date(2026, 2, 16),
                7.8,
                84,
                4.0,
                "NW",
                148,
                330.0,
                distance_km,
                2706,
            ),
            # Query 2: hr_efficiency (C1 expanded)
            (
                "aerobic_base",  # training_type
                "Zone 3",  # primary_zone
                "appropriate",  # zone_distribution_rating
                "stable",  # hr_stability
                "good",  # aerobic_efficiency
                "effective",  # training_quality
                False,  # zone2_focus
                False,  # zone4_threshold_work
                5.2,  # zone1_percentage
                36.8,  # zone2_percentage
                50.5,  # zone3_percentage
                5.0,  # zone4_percentage
                2.5,  # zone5_percentage
            ),
            # Query 3: elevation
            # (total_gain, total_loss, split_count,
            #  max_split_change, max_split_gain, max_split_loss)
            (12.8, 11.2, 8, 4.5, 2.5, 2.0),
            # Query 4: form_evaluations (C2)
            (
                "★★★★★",  # gct_star_rating
                4.8,  # gct_score
                "★★★★☆",  # vo_star_rating
                4.0,  # vo_score
                "★★★★☆",  # vr_star_rating
                4.0,  # vr_score
                92.5,  # integrated_score
                4.3,  # overall_score
                "★★★★☆",  # overall_star_rating
            ),
            # Query 5: performance_trends (C3)
            (
                0.017,
                2.5,
                "stable",
                "none",
                "6:33/km",
                134.0,
                "1,2",
                "5:45/km",
                155.0,
                "3,4,5,6",
                None,
                None,
                None,
                "7:12/km",
                140.0,
                "7,8",
            ),
        ]

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_full_context_returned(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Test that all C1-C3 fields are returned."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        result = prefetch_activity_context(12345)

        assert result["activity_id"] == 12345
        assert result["activity_date"] == "2026-02-16"
        assert result["training_type"] == "aerobic_base"
        assert result["temperature_c"] == 7.8
        assert result["terrain_category"] == "flat"
        assert result["max_split_elevation_gain"] == 2.5
        assert result["max_split_elevation_loss"] == 2.0

        # C1: zone_percentages and HR efficiency fields
        assert result["zone_percentages"]["zone1"] == 5.2
        assert result["zone_percentages"]["zone3"] == 50.5
        assert result["primary_zone"] == "Zone 3"
        assert result["zone_distribution_rating"] == "appropriate"
        assert result["hr_stability"] == "stable"
        assert result["aerobic_efficiency"] == "good"
        assert result["training_quality"] == "effective"
        assert result["zone2_focus"] is False
        assert result["zone4_threshold_work"] is False

        # C2: form_scores
        assert result["form_scores"]["gct"]["star_rating"] == "★★★★★"
        assert result["form_scores"]["gct"]["score"] == 4.8
        assert result["form_scores"]["vo"]["score"] == 4.0
        assert result["form_scores"]["vr"]["score"] == 4.0
        assert result["form_scores"]["integrated_score"] == 92.5
        assert result["form_scores"]["overall_score"] == 4.3
        assert result["form_scores"]["overall_star_rating"] == "★★★★☆"

        # Plan vs actual removed (Issue #785): no plan keys in the bundle.
        assert "plan_achievement" not in result
        assert "planned_workout" not in result

        # C3: phase_structure
        assert result["phase_structure"]["pace_consistency"] == 0.017
        assert result["phase_structure"]["hr_drift_percentage"] == 2.5
        assert result["phase_structure"]["warmup"]["avg_pace"] == "6:33/km"
        assert result["phase_structure"]["run"]["avg_hr"] == 155.0
        assert "recovery" not in result["phase_structure"]
        assert result["phase_structure"]["cooldown"]["avg_pace"] == "7:12/km"

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_bundle_has_no_plan_keys(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Plan vs actual removed (Issue #785): bundle has no plan_* keys.

        phase_category / next_run_target still resolve from training_type with
        planned_workout implicitly None.
        """
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        result = prefetch_activity_context(12345)

        assert "planned_workout" not in result
        assert "plan_achievement" not in result
        # Generic derivations still work with no plan.
        assert result["phase_category"] == "low_moderate"
        assert result["next_run_target"]["recommended_type"] == "easy"

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_activity_not_found(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Test error when activity not found."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None

        result = prefetch_activity_context(99999)

        assert "error" in result

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_missing_hr_efficiency(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Test graceful handling when hr_efficiency row is missing."""
        import datetime

        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.side_effect = [
            # activity
            (datetime.date(2026, 2, 16), 7.8, 84, 4.0, "NW", 148, 330.0, 8.2, 2706),
            None,  # hr_efficiency missing
            (None, None, 0, None, None, None),  # elevation (no splits)
            None,  # form_evaluations missing
            None,  # performance_trends missing
        ]

        result = prefetch_activity_context(12345)

        assert result["training_type"] is None
        assert result["zone_percentages"] is None
        assert result["primary_zone"] is None
        assert result["form_scores"] is None
        assert result["phase_structure"] is None

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_form_evaluations_table_missing(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Test graceful handling when form_evaluations table doesn't exist."""
        import datetime

        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:  # activity metadata
                mock_result.fetchone.return_value = (
                    datetime.date(2026, 2, 16),
                    7.8,
                    84,
                    4.0,
                    "NW",
                    148,
                    330.0,
                    8.2,
                    2706,
                )
            elif call_count == 2:  # hr_efficiency missing
                mock_result.fetchone.return_value = None
            elif call_count == 3:  # elevation
                mock_result.fetchone.return_value = (None, None, 0, None, None, None)
            elif call_count == 4:  # form_evaluations table missing
                raise duckdb.CatalogException(
                    "Table with name form_evaluations does not exist"
                )
            elif call_count == 5:  # performance_trends table missing
                raise duckdb.CatalogException(
                    "Table with name performance_trends does not exist"
                )
            return mock_result

        mock_conn.execute.side_effect = side_effect

        result = prefetch_activity_context(12345)

        assert result["form_scores"] is None
        assert result["phase_structure"] is None
        assert "error" not in result

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_query_error_propagates(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Non-catalog errors (e.g. BinderException) propagate to the caller."""
        import datetime

        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:  # activity metadata
                mock_result.fetchone.return_value = (
                    datetime.date(2026, 2, 16),
                    7.8,
                    84,
                    4.0,
                    "NW",
                    148,
                    330.0,
                    8.2,
                    2706,
                )
            elif call_count == 3:  # elevation
                mock_result.fetchone.return_value = (None, None, 0, None, None, None)
            elif call_count == 4:  # form_evaluations query is broken
                raise duckdb.BinderException(
                    'Referenced column "gct_star_rating" not found'
                )
            else:
                mock_result.fetchone.return_value = None
            return mock_result

        mock_conn.execute.side_effect = side_effect

        with pytest.raises(duckdb.BinderException):
            prefetch_activity_context(12345)

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_full_context_regression(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """All tables present -> every key stays filled (no plan keys)."""
        import datetime

        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.side_effect = [
            # Query 1: activity metadata
            (datetime.date(2026, 2, 16), 7.8, 84, 4.0, "NW", 148, 330.0, 8.2, 2706),
            # Query 2: hr_efficiency
            (
                "aerobic_base",
                "Zone 3",
                "appropriate",
                "stable",
                "good",
                "effective",
                False,
                False,
                5.2,
                36.8,
                50.5,
                5.0,
                2.5,
            ),
            # Query 3: elevation
            (12.8, 11.2, 8, 4.5, 2.5, 2.0),
            # Query 4: form_evaluations
            ("★★★★★", 4.8, "★★★★☆", 4.0, "★★★★☆", 4.0, 92.5, 4.3, "★★★★☆"),
            # Query 5: performance_trends
            (
                0.017,
                2.5,
                "stable",
                "none",
                "6:33/km",
                134.0,
                "1,2",
                "5:45/km",
                155.0,
                "3,4,5,6",
                None,
                None,
                None,
                "7:12/km",
                140.0,
                "7,8",
            ),
        ]

        result = prefetch_activity_context(12345)

        assert "error" not in result
        # Plan vs actual removed (Issue #785): no plan keys in the bundle.
        assert "planned_workout" not in result
        assert "plan_achievement" not in result
        # form_scores and phase_structure stay filled as before
        assert result["form_scores"]["gct"]["score"] == 4.8
        assert result["form_scores"]["overall_star_rating"] == "★★★★☆"
        assert result["phase_structure"]["pace_consistency"] == 0.017
        assert result["phase_structure"]["run"]["avg_hr"] == 155.0
        # existing scalar keys unaffected
        assert result["activity_date"] == "2026-02-16"
        assert result["training_type"] == "aerobic_base"
        assert result["terrain_category"] == "flat"

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_activity_context_long_run_gate_only_for_long_runs(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """long_run_gate is null below 10 km and a verdict at/above it (#982)."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        # 5 km run -> the gate has no basis, so the key stays null.
        self._setup_basic_queries(mock_conn, distance_km=5.0)
        with patch(
            "garmin_mcp.analysis.progression_gate.build_long_run_progression_gate"
        ) as build:
            short_run = prefetch_activity_context(12345)
        assert short_run["long_run_gate"] is None
        build.assert_not_called()

        # 19 km run -> the deterministic verdict rides along in the bundle.
        self._setup_basic_queries(mock_conn, distance_km=19.0)
        gate = {
            "activity_id": 12345,
            "current": {"gct_fade_ms": 4.0},
            "reference": None,
            "verdict": "green",
            "recommendation": "extend",
            "triggers": [],
            "decoupling_contaminated": False,
            "reference_activity_id": None,
            "reason_ja": "後半の脚の崩れは基準内です。次のロングは延長できます。",
        }
        with (
            patch(
                "garmin_mcp.database.readers.durability.DurabilityReader"
            ) as reader_cls,
            patch(
                "garmin_mcp.analysis.progression_gate."
                "build_long_run_progression_gate",
                return_value=gate,
            ) as build,
        ):
            long_run = prefetch_activity_context(12345)

        assert long_run["long_run_gate"]["verdict"] == "green"
        assert long_run["long_run_gate"]["recommendation"] == "extend"
        build.assert_called_once_with(reader_cls.return_value, 12345)

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_activity_context_includes_prescription_layer(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """A prescribed day carries the verdict, week position and deltas (#984)."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn, distance_km=8.2)

        plan_reader = MagicMock()
        plan_reader.get_prescriptions_for_date.return_value = [
            {
                "date": "2026-02-16",
                "session_type": "easy",
                "title": "イージー 8km",
                "target_km": 8.0,
                "hr_high": 150,
            }
        ]
        plan_reader.resolve_week_start.return_value = "2026-02-16"
        plan_reader.get_block_for_date.return_value = {"phase": "base"}
        plan_reader.get_ladder_step_for_week.return_value = {
            "current": {"week_start": "2026-02-16", "target_km": 19.0, "kind": "build"},
            "previous": None,
            "next": {"week_start": "2026-02-23", "target_km": 22.0, "kind": "build"},
        }
        previous = {
            "activity_id": 12000,
            "activity_date": "2026-02-09",
            "pace_s_per_km": 340.0,
            "avg_hr": 151,
            "gct_ms": 266.0,
            "cadence_spm": 170.0,
            "decoupling_pct": None,
        }
        wellness = {
            "date": "2026-02-16",
            "readiness": 72,
            "resting_hr": 46,
            "hrv_ms": 58.0,
            "sleep_score": 81,
            "readiness_z": 0.4,
            "rhr_z": -0.2,
            "hrv_z": 0.1,
            "adverse": False,
        }

        with (
            patch(
                "garmin_mcp.database.readers.plan.PlanReader",
                return_value=plan_reader,
            ),
            patch(
                "garmin_mcp.scripts.prefetch_activity_context."
                "_fetch_previous_same_type",
                return_value=previous,
            ),
            patch(
                "garmin_mcp.scripts.prefetch_activity_context._fetch_morning_wellness",
                return_value=wellness,
            ),
        ):
            result = prefetch_activity_context(12345)

        assert "error" not in result
        # 8.2 km against an 8.0 km easy prescription at 148 bpm under a 150 bpm
        # ceiling: the run answered the plan.
        assert result["prescription_verdict"]["verdict"] == "✅"
        assert result["prescription_verdict"]["prescription_title"] == "イージー 8km"
        assert result["prescription"][0]["session_type"] == "easy"
        assert result["week_position"]["week_start"] == "2026-02-16"
        assert result["week_position"]["ladder_step"]["next"]["target_km"] == 22.0
        assert result["week_position"]["block_phase"] == "base"
        assert result["previous_same_type"]["activity_id"] == 12000
        assert result["vs_previous"]["avg_hr"]["delta"] == -3
        assert result["vs_previous"]["days_ago"] == 7
        assert result["morning_wellness"]["readiness"] == 72

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_activity_context_layer_null_without_data(
        self,
        mock_get_conn: MagicMock,
        mock_get_db: MagicMock,
        mock_conn: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No plan ledger and no wellness row -> empty layer, never an error."""
        # A DB path that does not exist: every layer reader fails, and the
        # bundle must still come back whole (null-on-error, Issue #235).
        mock_get_db.return_value = str(tmp_path / "absent.duckdb")
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn, distance_km=8.2)

        result = prefetch_activity_context(12345)

        assert "error" not in result
        assert result["prescription"] == []
        for key in (
            "week_position",
            "previous_same_type",
            "vs_previous",
            "morning_wellness",
            "prescription_verdict",
        ):
            assert result[key] is None, key
