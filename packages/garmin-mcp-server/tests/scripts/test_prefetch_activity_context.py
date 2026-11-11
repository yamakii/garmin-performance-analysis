"""Tests for prefetch_activity_context script."""

import datetime
import inspect
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from garmin_mcp.analysis.current_standing import build_current_standing
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.scripts.prefetch_activity_context import (
    build_run_note_context,
    prefetch_activity_context,
)

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
        """Every key the run-note subset forwards exists in the bundle.

        build_run_note_context reads ``bundle.get(<key>)``; a key renamed or
        dropped on this side would silently reach the agent as null.
        """
        mock_get_db.return_value = "/fake/db.duckdb"
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        self._setup_basic_queries(mock_conn)

        source = inspect.getsource(build_run_note_context)
        read_keys = set(re.findall(r'\bbundle\.get\("([a-z_0-9]+)"\)', source))

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
            "athlete_context",
            "coaching_rules",
            "standing",
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


# The 2026-09-18 bundle, trimmed to the keys the subset cares about plus bulk
# that must NOT reach the run-note agent.
_BUNDLE = {
    "activity_id": 24407019887,
    "activity_date": "2026-09-18",
    "training_type": "easy",
    "week_position": {"days_to_long_run": 3, "cutback_week": False},
    "prescription": [{"prescription_id": 61}],
    "prescription_for_run": {
        "prescription_id": 61,
        "session_type": "easy",
        "title": "イージー 8km",
        "target_km": 8.0,
        "target_minutes": 50,
        "hr_low": 130,
        "hr_high": 150,
        "rationale": "週末のロングに向けて脚を回復させる",
        "garmin_workout_id": 1691891896,
    },
    "prescription_verdict": {"verdict": "✅"},
    "morning_wellness": {"readiness": 72},
    "vs_previous": {"pace_delta_s_per_km": -6.0},
    "previous_same_type": {"activity_date": "2026-09-15"},
    "similar_workouts": {
        "target_activity": {"activity_id": 24407019887},
        "similar_activities": [{"activity_id": i} for i in range(1, 6)],
    },
    "gear": {"gear_nickname": "v15"},
    "long_run_gate": None,
}


@pytest.mark.unit
class TestBuildRunNoteContext:
    """The coach subset handed to the run-note agent (#1362)."""

    def test_build_run_note_context_keeps_only_the_coach_subset(self) -> None:
        out = build_run_note_context(_BUNDLE)

        assert out is not None
        assert set(out) == {
            "training_type",
            "week_position",
            "prescription_for_run",
            "morning_wellness",
            "vs_previous",
            "previous_same_type",
            "similar_workouts",
            "gear",
            "long_run_gate",
            "athlete_context",
            "coaching_rules",
            "standing",
        }
        # Row bookkeeping stays out; the coaching fields stay in.
        assert out["prescription_for_run"] == {
            "title": "イージー 8km",
            "session_type": "easy",
            "target_km": 8.0,
            "target_minutes": 50,
            "hr_low": 130,
            "hr_high": 150,
            "rationale": "週末のロングに向けて脚を回復させる",
            # What the steps asked for (#1406); absent on this legacy row.
            "structure": None,
            "purpose": None,
            "strides": None,
        }
        # Top 3 similar workouts only -- context for one sentence, not a table.
        assert [s["activity_id"] for s in out["similar_workouts"]] == [1, 2, 3]
        assert out["gear"] == {"gear_nickname": "v15"}

    def test_build_run_note_context_handles_missing_prescription_and_similar(
        self,
    ) -> None:
        bundle = {**_BUNDLE, "prescription_for_run": None, "similar_workouts": None}

        out = build_run_note_context(bundle)

        assert out is not None
        assert out["prescription_for_run"] is None
        assert out["similar_workouts"] is None

    def test_build_run_note_context_returns_none_for_an_error_bundle(self) -> None:
        assert build_run_note_context({"error": "Activity 1 not found"}) is None
        assert build_run_note_context(None) is None

    def test_build_run_note_context_carries_athlete_context_and_rules(self) -> None:
        """The stated load and only the all / run_note rules reach the agent (#1522)."""
        athlete_context = {
            "items": [
                {
                    "kind": "load",
                    "value": "running backpack",
                    "load_kg": 3.0,
                    "source": "athlete_stated",
                    "note": None,
                }
            ],
            "inferred": {"commute": True},
            "load_kg": 3.0,
        }
        rules = [
            {
                "rule_id": 1,
                "user_id": "default",
                "scope": "all",
                "rule_text": "Read a loaded run as loaded, not as a form change.",
                "rationale": "2026-10-30 backpack run",
                "active": True,
                "created_at": "2026-11-07 12:00:00",
            },
            {
                "rule_id": 2,
                "user_id": "default",
                "scope": "run_note",
                "rule_text": "Name the stated load before any form signal.",
                "rationale": None,
                "active": True,
                "created_at": "2026-11-07 12:00:00",
            },
            {
                "rule_id": 3,
                "user_id": "default",
                "scope": "checkin",
                "rule_text": "Ask about the legs before the plan.",
                "rationale": None,
                "active": True,
                "created_at": "2026-11-07 12:00:00",
            },
        ]
        bundle = {
            **_BUNDLE,
            "athlete_context": athlete_context,
            "coaching_rules": rules,
        }

        out = build_run_note_context(bundle)

        assert out is not None
        assert out["athlete_context"] == athlete_context
        assert [rule["rule_id"] for rule in out["coaching_rules"]] == [1, 2]
        assert out["coaching_rules"][0] == {
            "rule_id": 1,
            "scope": "all",
            "rule_text": "Read a loaded run as loaded, not as a form change.",
            "rationale": "2026-10-30 backpack run",
        }

    def test_build_run_note_context_rules_empty_without_rules(self) -> None:
        """A bundle without rules (older DB, failed read) gives an empty list."""
        out = build_run_note_context({**_BUNDLE, "coaching_rules": None})

        assert out is not None
        assert out["coaching_rules"] == []
        assert out["athlete_context"] is None

    def test_run_note_context_includes_standing(self) -> None:
        """The goal, the block and what is proven reach the agent (#1572)."""
        standing = build_current_standing(
            on_date="2026-09-18",
            goals=[
                {
                    "race_name": "新潟シティマラソン",
                    "race_date": "2026-10-11",
                    "priority": "A",
                    "goal_type": "time",
                    "distance_km": 42.195,
                    "target_time_seconds": 18000,
                    "status": "active",
                }
            ],
            blocks=[
                {
                    "title": "Build",
                    "phase": "build",
                    "purpose": "ロングを30kmまで伸ばす",
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-28",
                    "long_run_ladder": [
                        {"week_start": "2026-09-14", "target_km": 24.0, "kind": "build"}
                    ],
                }
            ],
            proven_long_run={"activity_id": 1, "distance_km": 28.0},
            build_baseline={"weekly_km": 40.0},
            recent_runs=[],
        )

        out = build_run_note_context({**_BUNDLE, "standing": standing})

        assert out is not None
        goal = out["standing"]["goals"][0]
        assert goal["goal_pace_sec_per_km"] == 426.6
        assert goal["race_name"] == "新潟シティマラソン"
        assert goal["weeks_to_race"] == 4
        assert out["standing"]["block"]["phase"] == "build"
        assert out["standing"]["block"]["current_step"]["target_km"] == 24.0
        assert set(out["standing"]["block"]) == {
            "phase",
            "purpose",
            "week_position",
            "current_step",
        }
        assert out["standing"]["proven"]["build_baseline_km"] == 40.0
        # Plan / trend parts stay with get_current_standing.
        assert "remaining_steps" not in out["standing"]
        assert "recent_near_goal_pace" not in out["standing"]

    def test_run_note_context_standing_none_on_failure(self) -> None:
        """A failed standing read leaves the key null and the rest unchanged."""
        without = build_run_note_context({**_BUNDLE, "standing": None})
        absent = build_run_note_context(_BUNDLE)

        assert without is not None
        assert without["standing"] is None
        assert without == absent


@pytest.mark.unit
@patch("garmin_mcp.scripts.prefetch_activity_context.get_db_path")
@patch("garmin_mcp.scripts.prefetch_activity_context.get_connection")
def test_run_note_context_standing_is_as_of_activity_date(
    mock_get_conn: MagicMock, mock_get_db: MagicMock, tmp_path: Path
) -> None:
    """A block that starts the day after the run is not the run's block (#1572)."""
    mock_get_db.return_value = str(tmp_path / "absent.duckdb")
    mock_conn = MagicMock()
    mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchone.side_effect = [
        (datetime.date(2026, 3, 1), 148, 330.0, 8.2, 2706),
        None,  # gear
        ("aerobic_base",),
    ]
    later_block = {
        "title": "Build",
        "phase": "build",
        "purpose": "build",
        "start_date": "2026-03-02",
        "end_date": "2026-03-29",
        "long_run_ladder": [],
    }
    seen_dates: list[str | None] = []

    def fake_standing(
        on_date: str | None = None, user_id: str = "default"
    ) -> dict[str, Any]:
        seen_dates.append(on_date)
        return build_current_standing(
            on_date=on_date or "2026-11-12",
            goals=[],
            blocks=[later_block],
            proven_long_run=None,
            build_baseline={},
            recent_runs=[],
        )

    reader = MagicMock()
    reader.get_current_standing.side_effect = fake_standing
    with patch(
        "garmin_mcp.scripts.prefetch_activity_context.StandingReader",
        return_value=reader,
    ):
        bundle = prefetch_activity_context(12345)

    assert seen_dates == ["2026-03-01"]
    context = build_run_note_context(bundle)
    assert context is not None
    assert context["standing"] is not None
    assert context["standing"]["block"] is None


@pytest.mark.unit
def test_previous_same_type_reports_incomparable_reason(tmp_path: Path) -> None:
    """A loaded previous run: HR and dynamics deltas dropped, and why (#1523)."""
    from garmin_mcp.scripts.prefetch_activity_context import (
        _collect_prescription_layer,
    )

    previous = {
        "activity_id": 12000,
        "activity_date": "2026-02-09",
        "pace_s_per_km": 340.0,
        "avg_hr": 151,
        "gct_ms": 266.0,
        "cadence_spm": 170.0,
        "decoupling_pct": None,
    }
    profiles = {
        12345: {"dynamics_source": "wrist", "hr_source": "wrist", "load_kg": None},
        12000: {"dynamics_source": "wrist", "hr_source": "wrist", "load_kg": 3.0},
    }
    with (
        patch(
            "garmin_mcp.scripts.prefetch_activity_context._fetch_previous_same_type",
            return_value=previous,
        ),
        patch(
            "garmin_mcp.scripts.prefetch_activity_context."
            "_fetch_comparability_profiles",
            return_value=profiles,
        ),
    ):
        layer = _collect_prescription_layer(
            str(tmp_path / "absent.duckdb"),
            12345,
            "2026-02-16",
            "aerobic_base",
            {
                "activity_id": 12345,
                "activity_date": "2026-02-16",
                "pace_s_per_km": 330.0,
                "avg_hr": 148,
                "gct_ms": 260.0,
                "cadence_spm": 172.0,
                "decoupling_pct": None,
            },
        )

    assert layer["previous_same_type"]["comparability"]["reasons"] == ["load_differs"]
    vs_previous = layer["vs_previous"]
    assert vs_previous["comparability"]["reasons"] == ["load_differs"]
    for dropped in ("avg_hr", "gct_ms", "pace_at_hr"):
        assert dropped not in vs_previous, dropped
    assert vs_previous["pace_s_per_km"]["delta"] == -10.0
