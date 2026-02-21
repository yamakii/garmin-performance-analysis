"""Tests for prefetch_activity_context module."""

from unittest.mock import MagicMock, patch

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


@pytest.mark.unit
class TestPrefetchActivityContext:
    """Test the main prefetch function with mocked DB."""

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create a mock DB connection."""
        return MagicMock()

    def _setup_basic_queries(self, mock_conn: MagicMock) -> None:
        """Set up mock return values for all 6 queries."""
        import datetime

        mock_conn.execute.return_value.fetchone.side_effect = [
            # Query 1: activity metadata
            (datetime.date(2026, 2, 16), 7.8, 84, 4.0, "NW"),
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
            # Query 3: planned_workout
            None,
            # Query 4: elevation
            (12.8, 11.2, 8),
            # Query 5: form_evaluations (C2)
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
            # Query 6: performance_trends (C3)
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

        # C3: phase_structure
        assert result["phase_structure"]["pace_consistency"] == 0.017
        assert result["phase_structure"]["hr_drift_percentage"] == 2.5
        assert result["phase_structure"]["warmup"]["avg_pace"] == "6:33/km"
        assert result["phase_structure"]["run"]["avg_hr"] == 155.0
        assert "recovery" not in result["phase_structure"]
        assert result["phase_structure"]["cooldown"]["avg_pace"] == "7:12/km"

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
            (datetime.date(2026, 2, 16), 7.8, 84, 4.0, "NW"),  # activity
            None,  # hr_efficiency missing
            None,  # planned_workout
            (0.0, 0.0, 0),  # elevation (no splits)
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
            if call_count == 1:
                mock_result.fetchone.return_value = (
                    datetime.date(2026, 2, 16),
                    7.8,
                    84,
                    4.0,
                    "NW",
                )
            elif call_count == 2 or call_count == 3:
                mock_result.fetchone.return_value = None
            elif call_count == 4:
                mock_result.fetchone.return_value = (0.0, 0.0, 0)
            elif call_count == 5:
                raise Exception("Table form_evaluations does not exist")
            elif call_count == 6:
                raise Exception("Table performance_trends does not exist")
            return mock_result

        mock_conn.execute.side_effect = side_effect

        result = prefetch_activity_context(12345)

        assert result["form_scores"] is None
        assert result["phase_structure"] is None
        assert "error" not in result
