"""Tests for the prefetch_weekly_review_context bundler (Issue #849).

Unit tests cover the pure week-resolution / weeks-to-race / bundle-trim helpers
and the additive null-on-error contract (mocked collaborators). Integration
tests seed a real DuckDB (via GarminDBWriter) and confirm every bundle key is
present, both activity windows resolve, the bundle is json-serializable, and the
collection is read-only (no rows written — catch_up_ingest is excluded).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _RECOVERY_SERIES_KEEP_DAYS,
    _resolve_target_week,
    _slim_athlete_profile,
    _slim_past_review,
    _slim_recovery_trend,
    _weeks_to_race,
    prefetch_weekly_review_context,
)

_MODULE = "garmin_mcp.scripts.prefetch_weekly_review_context"


# ── Unit: week resolution ────────────────────────────────────────────────


@pytest.mark.unit
def test_resolve_target_week_default_midweek() -> None:
    """None target mid-week -> the current (in-progress) week."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 6), date(2026, 7, 12))
    assert (ps, pe) == (date(2026, 6, 29), date(2026, 7, 5))
    assert in_progress is True


@pytest.mark.unit
def test_resolve_target_week_default_last_day() -> None:
    """None target on the last day (Sunday) -> next week, not in progress."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 6, 14), 0)
    assert (ws, we) == (date(2026, 6, 15), date(2026, 6, 21))
    assert (ps, pe) == (date(2026, 6, 8), date(2026, 6, 14))
    assert in_progress is False


@pytest.mark.unit
def test_resolve_target_week_this() -> None:
    """'this' -> the week containing today."""
    ws, we, _ps, _pe, _ip = _resolve_target_week("this", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 6), date(2026, 7, 12))


@pytest.mark.unit
def test_resolve_target_week_next() -> None:
    """'next' -> the week after the one containing today."""
    ws, we, _ps, _pe, in_progress = _resolve_target_week("next", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 13), date(2026, 7, 19))
    assert in_progress is False


@pytest.mark.unit
def test_resolve_target_week_explicit() -> None:
    """An explicit YYYY-MM-DD -> the week containing that date."""
    ws, we, _ps, _pe, _ip = _resolve_target_week("2026-06-16", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 6, 15), date(2026, 6, 21))


@pytest.mark.unit
def test_resolve_target_week_sunday_start() -> None:
    """Sunday-start weeks: Saturday is the last day -> next week's bounds."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 6, 20), 6)
    assert (ws, we) == (date(2026, 6, 21), date(2026, 6, 27))
    assert (ps, pe) == (date(2026, 6, 14), date(2026, 6, 20))
    assert in_progress is False


# ── Unit: weeks to race ──────────────────────────────────────────────────


@pytest.mark.unit
def test_weeks_to_race_confirmed() -> None:
    """A confirmed race date -> ceil((race - week_start) / 7) whole weeks."""
    assert _weeks_to_race("2026-10-11", date(2026, 7, 6)) == 14


@pytest.mark.unit
def test_weeks_to_race_null() -> None:
    """A missing race date -> None (unconfirmed race)."""
    assert _weeks_to_race(None, date(2026, 7, 6)) is None


# ── Unit: bundle contract (mocked collaborators) ─────────────────────────


@contextmanager
def _mock_prefetch(
    load_trend_raises: bool = False,
    profile: dict[str, Any] | None = None,
    past_review: dict[str, Any] | None = None,
) -> Iterator[MagicMock]:
    """Patch every prefetch collaborator so the bundle can run without a DB.

    Args:
        load_trend_raises: Make ``get_load_trend`` raise (null-on-error probe).
        profile: Athlete profile the ``AthleteReader`` returns (defaults to a
            goal-less profile).
        past_review: Past review the ``AthleteReader`` returns (defaults to
            ``None``, i.e. no previous review).

    Yields the ``GarminDBReader`` mock so a test can flip one reader to raise
    and assert the additive null-on-error contract.
    """
    reader = MagicMock()
    if load_trend_raises:
        reader.get_load_trend.side_effect = RuntimeError("boom")
    else:
        reader.get_load_trend.return_value = {"weeks": []}
    reader.get_acwr.return_value = {"acwr": 1.0}
    reader.get_recovery_trend.return_value = {"weeks": 8}
    reader.get_recovery_status.return_value = {"recommendation": "easy"}
    reader.get_wellness_baseline_deviation.return_value = {"overall_flag": False}
    reader.get_strength_sessions.return_value = []
    reader.get_hiking_sessions.return_value = []

    athlete_reader = MagicMock()
    athlete_reader.get_athlete_profile.return_value = (
        {"goals": []} if profile is None else profile
    )
    athlete_reader.get_weekly_review.return_value = past_review

    assessor = MagicMock()
    assessor.assess.return_value.model_dump.return_value = {"vdot": 50.0}

    with (
        patch(f"{_MODULE}.get_db_path", return_value=Path("/tmp/wr_unit.duckdb")),
        patch(f"{_MODULE}.get_connection"),
        patch(f"{_MODULE}.get_week_start_day", return_value=0),
        patch(f"{_MODULE}._resolve_activities", return_value=[]),
        patch(
            "garmin_mcp.database.db_reader.GarminDBReader",
            return_value=reader,
        ),
        patch(
            "garmin_mcp.database.readers.athlete.AthleteReader",
            return_value=athlete_reader,
        ),
        patch(
            "garmin_mcp.fitness.fitness_assessor.FitnessAssessor",
            return_value=assessor,
        ),
        patch(
            "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader",
            side_effect=RuntimeError("no network"),
        ),
    ):
        yield reader


@pytest.mark.unit
def test_prefetch_bundle_safe_null_on_reader_error() -> None:
    """One failing reader nulls its key; the rest of the bundle survives."""
    with _mock_prefetch(load_trend_raises=True):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    # The failing collector is null; siblings are populated.
    assert result["load_trend"] is None
    assert result["acwr"] == {"acwr": 1.0}
    # Network calendar reader raised -> null, but the key is still present.
    assert result["scheduled_workouts"] is None
    for key in (
        "week_start_date",
        "week_end_date",
        "prev_start",
        "prev_end",
        "week_in_progress",
        "week_start_day",
        "as_of",
        "activity_ids",
        "activities",
        "fitness_summary",
        "recovery",
        "strength",
        "hiking",
        "athlete_profile",
        "goals_with_weeks_to_race",
        "past_review",
    ):
        assert key in result


@pytest.mark.unit
def test_prefetch_bundle_has_hiking_key() -> None:
    """The bundle carries hiking.{prev_week, current_week} (issue #921)."""
    with _mock_prefetch() as reader:
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert set(result["hiking"]) == {"prev_week", "current_week"}
    assert result["hiking"] == {"prev_week": [], "current_week": []}
    # Both windows are read from the hiking reader (W-1 and W).
    assert reader.get_hiking_sessions.call_count == 2
    assert reader.get_hiking_sessions.call_args_list[0].args == (
        "2026-06-29",
        "2026-07-05",
    )
    assert reader.get_hiking_sessions.call_args_list[1].args == (
        "2026-07-06",
        "2026-07-12",
    )


def _weeks(series: list[tuple[str, int | None]]) -> dict[str, Any]:
    """Build a minimal ``get_load_trend`` result from (week_start, longest) pairs."""
    return {"weeks": [{"week_start": ws, "longest_run_sec": sec} for ws, sec in series]}


@pytest.mark.unit
def test_prefetch_bundle_long_run_gate() -> None:
    """load_trend.long_run carries the deterministic cutback gate (#927)."""
    weekly_longest = [3250, 7819, 8125, 8562]
    # Four completed weeks, all before W (2026-07-06).
    week_starts = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29"]
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            list(zip(week_starts, weekly_longest, strict=True))
        )
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == weekly_longest
    # Three straight >= +3% extensions -> the primary cutback gate fires.
    assert long_run["long_run_build_weeks"] == 3
    assert long_run["cutback_due_long_run"] is True


@pytest.mark.unit
def test_long_run_gate_excludes_in_progress_week() -> None:
    """W's own partial bucket must not reset the streak (#929).

    ``get_load_trend`` ends at today, so a Monday review sees W's bucket with
    ``longest_run_sec: None`` (the week's long run has not happened yet). That
    ``None`` used to read as a no-run week and zero the gate.
    """
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            [
                ("2026-07-20", 3250),
                ("2026-07-27", 7819),
                ("2026-08-03", 8125),
                ("2026-08-10", 8562),
                ("2026-08-17", None),  # W itself, still in progress
            ]
        )
        result = prefetch_weekly_review_context("this", today="2026-08-17")

    assert result["week_start_date"] == "2026-08-17"
    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == [3250, 7819, 8125, 8562]
    assert long_run["long_run_build_weeks"] == 3
    assert long_run["cutback_due_long_run"] is True


@pytest.mark.unit
def test_long_run_gate_keeps_none_for_completed_norun_week() -> None:
    """A completed week with no run is still a reset boundary (#929)."""
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            [
                ("2026-07-27", 7200),
                ("2026-08-03", None),  # completed week, genuinely no run
                ("2026-08-10", 7500),
            ]
        )
        result = prefetch_weekly_review_context("this", today="2026-08-17")

    long_run = result["load_trend"]["long_run"]
    assert long_run["weekly_longest_sec"] == [7200, None, 7500]
    assert long_run["long_run_build_weeks"] == 0
    assert long_run["cutback_due_long_run"] is False


@pytest.mark.unit
def test_prefetch_weekly_review_long_run_gate() -> None:
    """W-1's longest run carries the progression verdict at load_trend (#982)."""
    prev_activities = [
        {
            "activity_id": 9101,
            "activity_date": "2026-06-30",
            "activity_name": "朝ジョグ",
            "distance_km": 8.0,
            "duration_seconds": 2600,
        },
        {
            "activity_id": 9102,
            "activity_date": "2026-07-05",
            "activity_name": "ロング走",
            "distance_km": 19.0,
            "duration_seconds": 7800,
        },
    ]
    gate = {
        "activity_id": 9102,
        "current": {"gct_fade_ms": 12.0},
        "reference": {"activity_id": 9003},
        "verdict": "yellow",
        "recommendation": "repeat",
        "triggers": [{"metric": "gct_fade_ms", "worse_than_reference": False}],
        "decoupling_contaminated": False,
        "reference_activity_id": 9003,
        "reason_ja": "次は同距離で反復してください。",
    }

    with (
        _mock_prefetch() as reader,
        patch(f"{_MODULE}._resolve_activities", side_effect=[prev_activities, []]),
        patch(f"{_MODULE}.build_long_run_progression_gate", return_value=gate) as build,
    ):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    long_run = result["load_trend"]["long_run"]
    assert long_run["gate"]["verdict"] == "yellow"
    assert long_run["gate"]["recommendation"] == "repeat"
    # The longest W-1 run is gated, not the 8 km jog.
    build.assert_called_once_with(reader, 9102)


@pytest.mark.unit
def test_prefetch_weekly_review_long_run_gate_null_without_long_run() -> None:
    """A W-1 with no run reaching 10 km leaves the gate null (#982)."""
    prev_activities = [
        {
            "activity_id": 9201,
            "activity_date": "2026-07-02",
            "activity_name": "朝ジョグ",
            "distance_km": 8.0,
            "duration_seconds": 2600,
        }
    ]

    with (
        _mock_prefetch(),
        patch(f"{_MODULE}._resolve_activities", side_effect=[prev_activities, []]),
        patch(f"{_MODULE}.build_long_run_progression_gate") as build,
    ):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["load_trend"]["long_run"]["gate"] is None
    build.assert_not_called()


@pytest.mark.unit
def test_prefetch_invalid_target_returns_error() -> None:
    """An unparseable target -> a fatal error bundle."""
    with (
        patch(f"{_MODULE}.get_db_path", return_value=Path("/tmp/wr_unit.duckdb")),
        patch(f"{_MODULE}.get_connection"),
        patch(f"{_MODULE}.get_week_start_day", return_value=0),
    ):
        result = prefetch_weekly_review_context("garbage", today="2026-07-10")

    assert "error" in result
    assert "garbage" in result["error"]


# ── Unit: bundle trims (Issue #933) ──────────────────────────────────────


@pytest.mark.unit
def test_slim_athlete_profile_drops_goals() -> None:
    """The profile's duplicate goals copy is dropped, everything else stays."""
    profile = {"goals": [{"race_name": "新潟"}], "focus_notes": "x"}

    slim = _slim_athlete_profile(profile)

    assert slim is not None
    assert "goals" not in slim
    assert slim["focus_notes"] == "x"
    # The reader's dict is untouched (the caller still derives goals from it).
    assert "goals" in profile
    assert _slim_athlete_profile(None) is None


@pytest.mark.unit
def test_slim_recovery_series_keeps_last_14_days() -> None:
    """Only the recent tail of the daily series survives; aggregates are kept."""
    start = date(2026, 6, 22)
    series = [
        {
            "date": str(start + timedelta(days=i)),
            "resting_hr": 48 + (i % 3),
            "hrv_overnight_ms": 60 + i,
        }
        for i in range(57)
    ]
    trend = {
        "weeks": 8,
        "rhr": {"median_7d": 48, "median_30d": 50, "rhr_trend": "stable"},
        "hrv": {"latest_ms": 62, "hrv_below_baseline_days": 1},
        "series": series,
    }

    slim = _slim_recovery_trend(trend)

    assert slim is not None
    assert len(slim["series"]) == _RECOVERY_SERIES_KEEP_DAYS == 14
    assert slim["series"] == series[-14:]
    # The latest day is retained (the tail, not the head, is what is read).
    assert slim["series"][-1]["date"] == str(start + timedelta(days=56))
    # 8-week aggregates are carried through unchanged (never recomputed).
    assert slim["rhr"] == trend["rhr"]
    assert slim["hrv"] == trend["hrv"]
    assert slim["weeks"] == 8
    # The reader's dict is untouched.
    assert len(series) == 57

    # A series-less trend (and None) passes through unchanged.
    no_series = {"weeks": 8, "rhr": {"median_7d": None}}
    assert _slim_recovery_trend(no_series) == no_series
    assert _slim_recovery_trend(None) is None


@pytest.mark.unit
def test_slim_past_review_drops_replay_keys() -> None:
    """Stale actuals/plan replays go; the continuity keys stay."""
    review = {
        "week_start_date": "2026-08-10",
        "review_data": {
            "this_week": {"volume_km": 30.0},
            "garmin_next_week": [{"date": "2026-08-11", "title": "Base"}],
            "verdict": [{"date": "2026-08-11", "rating": "✅"}],
            "recommendations": ["Z2 141-152bpm で 60 分"],
        },
    }

    slim = _slim_past_review(review)

    assert slim is not None
    assert "this_week" not in slim["review_data"]
    assert "garmin_next_week" not in slim["review_data"]
    assert slim["review_data"]["verdict"] == [{"date": "2026-08-11", "rating": "✅"}]
    assert slim["review_data"]["recommendations"] == ["Z2 141-152bpm で 60 分"]
    assert slim["week_start_date"] == "2026-08-10"
    # The reader's dict is untouched.
    assert "this_week" in review["review_data"]

    # A non-dict review_data (and None) passes through unchanged.
    raw = {"review_data": '{"this_week": {}}'}
    assert _slim_past_review(raw) == raw
    assert _slim_past_review(None) is None


@pytest.mark.unit
def test_prefetch_bundle_goals_single_copy() -> None:
    """Goals ship once, in goals_with_weeks_to_race (not in athlete_profile)."""
    profile = {
        "current_focus": "base",
        "goals": [{"race_name": "新潟", "race_date": "2026-10-11"}],
    }
    with _mock_prefetch(profile=profile):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "goals" not in result["athlete_profile"]
    assert result["athlete_profile"]["current_focus"] == "base"

    goals = result["goals_with_weeks_to_race"]
    assert len(goals) == 1
    assert goals[0]["race_name"] == "新潟"
    assert goals[0]["weeks_to_race"] == _weeks_to_race("2026-10-11", date(2026, 7, 6))


@pytest.mark.unit
def test_prefetch_bundle_trims_recovery_series_and_past_review() -> None:
    """The recovery-series / past-review trims are wired into the bundle."""
    series = [
        {"date": str(date(2026, 5, 15) + timedelta(days=i)), "resting_hr": 48}
        for i in range(57)
    ]
    past_review = {
        "week_start_date": "2026-06-29",
        "review_data": {
            "this_week": {"volume_km": 30.0},
            "garmin_next_week": [{"date": "2026-06-30", "title": "Base"}],
            "overall": "順調に積めています",
        },
    }
    with _mock_prefetch(past_review=past_review) as reader:
        reader.get_recovery_trend.return_value = {"weeks": 8, "series": series}
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["recovery"]["trend"]["series"] == series[-14:]
    assert set(result["past_review"]["review_data"]) == {"overall"}


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("prefetch_wr_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "prefetch_wr_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target


def _insert_activity(db_path: Path, activity_id: int, activity_date: str) -> None:
    with get_write_connection(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, activity_name,
                total_distance_km, total_time_seconds
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (activity_id, activity_date, "Run", 8.0, 2880),
        )


def _seed_profile_and_goal(db_path: Path) -> None:
    from garmin_mcp.database.inserters.athlete import insert_athlete_profile

    insert_athlete_profile(
        profile={
            "user_id": "default",
            "current_focus": "base",
            "week_start_day": 0,
            "goals": [
                {
                    "race_name": "Niigata",
                    "race_date": "2026-10-11",
                    "priority": "B",
                    "goal_type": "marathon",
                    "distance_km": 42.195,
                    "target_time_seconds": 12600,
                    "status": "active",
                }
            ],
        },
        db_path=str(db_path),
    )


def _row_count(db_path: Path) -> int:
    with get_write_connection(str(db_path)) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
        assert rows is not None
        return int(rows[0])


@contextmanager
def _no_network(db_path: Path) -> Iterator[None]:
    """Route get_db_path to the seeded DB and stub the network calendar reader."""
    with (
        patch(f"{_MODULE}.get_db_path", return_value=db_path),
        patch(
            "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader",
            side_effect=RuntimeError("no network in tests"),
        ),
    ):
        yield


@pytest.mark.integration
def test_prefetch_weekly_review_context_end_to_end(db_path: Path) -> None:
    """A seeded W-1/W -> all keys present, both windows resolved, serializable."""
    # W = 2026-07-06..07-12 (this week for today=07-10); W-1 = 06-29..07-05.
    _insert_activity(db_path, 849000001, "2026-07-01")  # prev week
    _insert_activity(db_path, 849000002, "2026-07-08")  # current week
    _seed_profile_and_goal(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    json.dumps(result, default=str)  # MCP-boundary serializable

    for key in (
        "week_start_date",
        "week_end_date",
        "prev_start",
        "prev_end",
        "week_in_progress",
        "week_start_day",
        "as_of",
        "activity_ids",
        "activities",
        "fitness_summary",
        "load_trend",
        "acwr",
        "recovery",
        "strength",
        "hiking",
        "scheduled_workouts",
        "athlete_profile",
        "goals_with_weeks_to_race",
        "past_review",
    ):
        assert key in result

    assert result["activity_ids"]["prev_week"] == [849000001]
    assert result["activity_ids"]["current_week"] == [849000002]
    assert {a["activity_id"] for a in result["activities"]} == {849000001, 849000002}

    # recovery is a nested triple of collectors.
    assert set(result["recovery"]) == {"trend", "status", "baseline_deviation"}

    # goals_with_weeks_to_race carries the pre-computed ceiling, and is the
    # bundle's only copy of the goals (Issue #933).
    goals = result["goals_with_weeks_to_race"]
    assert len(goals) == 1
    assert goals[0]["weeks_to_race"] == _weeks_to_race("2026-10-11", date(2026, 7, 6))
    assert "goals" not in result["athlete_profile"]


@pytest.mark.integration
def test_prefetch_is_read_only(db_path: Path) -> None:
    """Collection writes nothing (catch_up_ingest is intentionally excluded)."""
    _insert_activity(db_path, 849000010, "2026-07-01")
    before = _row_count(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    assert _row_count(db_path) == before
