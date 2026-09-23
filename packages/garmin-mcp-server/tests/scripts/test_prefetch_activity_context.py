"""Tests for prefetch_activity_context script."""

import datetime
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.scripts.prefetch_activity_context import prefetch_activity_context

REPO_ROOT = Path(__file__).resolve().parents[4]

# Activity row: (date, avg_hr, avg_pace_s_per_km, total_distance_km,
# total_time_seconds).
ACTIVITY_ROW = (datetime.date(2026, 2, 16), 148, 330.0, 8.2, 2706)


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
        """Set up mock return values for the three queries of the read block."""
        mock_conn.execute.return_value.fetchone.side_effect = [
            # Query 1: activity metadata
            (*ACTIVITY_ROW[:3], distance_km, ACTIVITY_ROW[4]),
            # Query 2: gear (type, model, nickname, first_use, runs, km,
            #  as_of, max_km, status, since, retired)
            (
                "Shoes",
                "Nike Vaporfly",
                None,
                datetime.date(2026, 2, 1),
                3,
                24.0,
                datetime.date(2026, 2, 16),
                643.7,
                "active",
                datetime.date(2026, 2, 1),
                None,
            ),
            # Query 3: hr_efficiency (training_type only)
            ("aerobic_base",),
        ]

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_context_returned(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """The envelope, the shoe and the always-present keys come back."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        result = prefetch_activity_context(12345)

        assert result["activity_id"] == 12345
        assert result["activity_date"] == "2026-02-16"
        assert result["training_type"] == "aerobic_base"
        assert result["gear"]["gear_model"] == "Nike Vaporfly"
        assert "similar_workouts" in result
        assert result["long_run_gate"] is None
        # The run itself is get_run_report's: none of the numbers the retired
        # section analysts read here are emitted any more (#1287).
        for gone in (
            "temperature_c",
            "terrain_category",
            "zone_percentages",
            "zone_distribution_score",
            "form_scores",
            "phase_structure",
            "phase_category",
            "next_run_target",
            "form_evaluation",
            "hr_zones_detail",
            "form_baseline_trend",
            "vo2_max",
            "lactate_threshold",
        ):
            assert gone not in result, gone

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
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.side_effect = [
            ACTIVITY_ROW,
            None,  # gear missing
            None,  # hr_efficiency missing
        ]

        result = prefetch_activity_context(12345)

        assert "error" not in result
        assert result["training_type"] is None
        assert result["gear"] is None

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_prefetch_query_error_propagates(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """A broken query in the read block propagates to the caller."""
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:  # activity metadata
                mock_result.fetchone.return_value = ACTIVITY_ROW
            elif call_count == 3:  # hr_efficiency query is broken
                raise duckdb.BinderException(
                    'Referenced column "training_type" not found'
                )
            else:
                mock_result.fetchone.return_value = None
            return mock_result

        mock_conn.execute.side_effect = side_effect

        with pytest.raises(duckdb.BinderException):
            prefetch_activity_context(12345)

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_form_baseline_self_heal_still_runs(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """The month's form baseline is still trained here when missing.

        This is the only caller of the self-heal (Issue #266) and ingest grades
        form against that baseline (#1088): trimming the bundle must not drop
        the side effect along with the key that used to report it (#1287).
        """
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        with patch(
            "garmin_mcp.form_baseline.trainer.ensure_form_baselines_for_date",
            return_value={"generated": [], "skipped": [], "insufficient": []},
        ) as ensure:
            result = prefetch_activity_context(12345)

        ensure.assert_called_once_with("2026-02-16", "/fake/db.duckdb")
        assert "form_baseline_autogen" not in result

        # A failing self-heal never takes the bundle down with it.
        self._setup_basic_queries(mock_conn)
        with patch(
            "garmin_mcp.form_baseline.trainer.ensure_form_baselines_for_date",
            side_effect=RuntimeError("locked"),
        ):
            result = prefetch_activity_context(12345)
        assert "error" not in result

    @patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
    @patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
    def test_workflow_context_keys_are_all_in_the_bundle(
        self, mock_get_conn: MagicMock, mock_get_db: MagicMock, mock_conn: MagicMock
    ) -> None:
        """Every key the analyze-activity workflow forwards exists in the bundle.

        buildRunNoteContext reads ``bundle.<key>``; a key renamed or dropped on
        this side would silently reach the agent as null.
        """
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        script = (REPO_ROOT / ".claude/workflows/analyze-activity.js").read_text()
        start = script.index("function buildRunNoteContext")
        end = script.index("\nfunction ", start + 1)
        read_keys = set(re.findall(r"\bbundle\.([a-z_0-9]+)", script[start:end]))

        assert read_keys == {
            "training_type",
            "week_position",
            "prescription_for_run",
            "morning_wellness",
            "vs_previous",
            "previous_same_type",
            "similar_workouts",
            "gear",
            "long_run_gate",
        }
        result = prefetch_activity_context(12345)
        assert read_keys <= set(result)

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
            "recovery_cost": None,
            "reason_ja": "後半の脚の崩れは基準内です。次のロングは延長できます。",
        }
        with patch(
            "garmin_mcp.analysis.progression_gate.build_long_run_progression_gate",
            return_value=gate,
        ) as build:
            long_run = prefetch_activity_context(12345)

        assert long_run["long_run_gate"]["verdict"] == "green"
        assert long_run["long_run_gate"]["recommendation"] == "extend"
        assert long_run["long_run_gate"]["recovery_cost"] is None
        build.assert_called_once()
        source, called_activity_id = build.call_args.args
        assert called_activity_id == 12345
        # The unified reader, since the gate also prices the next two mornings.
        assert isinstance(source, GarminDBReader)

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
            patch(
                "garmin_mcp.scripts.prefetch_activity_context._fetch_previous_day_run",
                return_value={"distance_km": 2.77, "duration_min": 20.0},
            ),
        ):
            result = prefetch_activity_context(12345)

        assert "error" not in result
        # Yesterday was a 2.77 km jog, so this is not the morning after a long
        # run, whatever the weekday (#1333).
        assert result["week_position"]["previous_day_run"]["distance_km"] == 2.77
        assert result["week_position"]["is_day_after_long_run"] is False
        # The plan verdict is the run report's alone (#1353): the bundle
        # carries what was prescribed, never a second judgement of it.
        assert "prescription_verdict" not in result
        assert result["prescription_for_run"]["title"] == "イージー 8km"
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
        ):
            assert result[key] is None, key
