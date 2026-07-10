"""Tests for the prefetch_weekly_review_context bundler (Issue #849).

Unit tests cover the pure week-resolution / weeks-to-race helpers and the
additive null-on-error contract (mocked collaborators). Integration tests seed a
real DuckDB (via GarminDBWriter) and confirm every bundle key is present, both
activity windows resolve, the bundle is json-serializable, and the collection is
read-only (no rows written — catch_up_ingest is intentionally excluded).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _resolve_target_week,
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
def _mock_prefetch(load_trend_raises: bool = False) -> Iterator[MagicMock]:
    """Patch every prefetch collaborator so the bundle can run without a DB.

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

    athlete_reader = MagicMock()
    athlete_reader.get_athlete_profile.return_value = {"goals": []}
    athlete_reader.get_weekly_review.return_value = None

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
        "athlete_profile",
        "goals_with_weeks_to_race",
        "past_review",
    ):
        assert key in result


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


# ── Integration: seeded DuckDB ───────────────────────────────────────────


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

    # goals_with_weeks_to_race carries the pre-computed ceiling.
    goals = result["goals_with_weeks_to_race"]
    assert len(goals) == 1
    assert goals[0]["weeks_to_race"] == _weeks_to_race("2026-10-11", date(2026, 7, 6))


@pytest.mark.integration
def test_prefetch_is_read_only(db_path: Path) -> None:
    """Collection writes nothing (catch_up_ingest is intentionally excluded)."""
    _insert_activity(db_path, 849000010, "2026-07-01")
    before = _row_count(db_path)

    with _no_network(db_path):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    assert _row_count(db_path) == before
