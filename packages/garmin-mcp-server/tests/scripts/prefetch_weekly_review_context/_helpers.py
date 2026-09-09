"""Shared helpers for the prefetch_weekly_review_context tests (split from test_prefetch_weekly_review_context.py, #1069)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from garmin_mcp.database.connection import get_write_connection

_MODULE = "garmin_mcp.scripts.prefetch_weekly_review_context"


@contextmanager
def _mock_prefetch(
    load_trend_raises: bool = False,
    profile: dict[str, Any] | None = None,
    past_review: dict[str, Any] | None = None,
    block: dict[str, Any] | None = None,
    ladder_step: dict[str, Any] | None = None,
    prev_prescriptions: list[dict[str, Any]] | None = None,
    prescriptions_by_week: dict[str, list[dict[str, Any]]] | None = None,
    scheduled: list[dict[str, Any]] | None = None,
) -> Iterator[MagicMock]:
    """Patch every prefetch collaborator so the bundle can run without a DB.

    Args:
        load_trend_raises: Make ``get_load_trend`` raise (null-on-error probe).
        profile: Athlete profile the ``AthleteReader`` returns (defaults to a
            goal-less profile).
        past_review: Past review the ``AthleteReader`` returns (defaults to
            ``None``, i.e. no previous review).
        block: Training block the ``PlanReader`` returns for W (defaults to
            ``None``, i.e. no block registered).
        ladder_step: ``{"current", "previous", "next"}`` the ``PlanReader``
            returns for W (defaults to ``None``).
        prev_prescriptions: W-1 prescription rows (defaults to none). Returned
            for every week; use ``prescriptions_by_week`` to differentiate.
        prescriptions_by_week: Rows keyed by week start, so W and W-1 can carry
            different batches (overrides ``prev_prescriptions``).
        scheduled: Garmin calendar items for W. ``None`` keeps the default
            "calendar unreachable" behaviour (the reader raises).

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

    plan_reader = MagicMock()
    plan_reader.get_block_for_date.return_value = block
    plan_reader.get_ladder_step_for_week.return_value = ladder_step
    if prescriptions_by_week is not None:
        by_week = prescriptions_by_week
        plan_reader.get_weekly_prescriptions.side_effect = (
            lambda week_start_date, user_id="default": list(
                by_week.get(week_start_date, [])
            )
        )
    else:
        plan_reader.get_weekly_prescriptions.return_value = prev_prescriptions or []

    if scheduled is None:
        calendar_patch = patch(
            "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader",
            side_effect=RuntimeError("no network"),
        )
    else:
        calendar_reader = MagicMock()
        calendar_reader.get_scheduled_workouts.return_value = scheduled
        calendar_patch = patch(
            "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader",
            return_value=calendar_reader,
        )

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
            "garmin_mcp.database.readers.plan.PlanReader",
            return_value=plan_reader,
        ),
        patch(
            "garmin_mcp.fitness.fitness_assessor.FitnessAssessor",
            return_value=assessor,
        ),
        calendar_patch,
    ):
        yield reader


def _block(
    phase: str = "build",
    end_date: str = "2026-09-27",
    quality_sessions_per_week: int | None = 1,
) -> dict[str, Any]:
    """A training block covering the 2026-09-07 week, with a 3-step ladder."""
    return {
        "block_id": 1,
        "phase": phase,
        "title": "新潟ビルド",
        "start_date": "2026-08-31",
        "end_date": end_date,
        "weight_mode": "維持",
        "quality_sessions_per_week": quality_sessions_per_week,
        "quality_types": ["threshold"],
        "long_run_ladder": [
            {"week_start": "2026-08-31", "target_km": 19.0},
            {"week_start": "2026-09-07", "target_km": 22.0},
            {"week_start": "2026-09-14", "target_km": 25.0},
        ],
    }


def _ladder(current_km: float = 22.0) -> dict[str, Any]:
    """The ladder step trio the PlanReader derives for the 2026-09-07 week."""
    return {
        "current": {"week_start": "2026-09-07", "target_km": current_km},
        "previous": {"week_start": "2026-08-31", "target_km": 19.0},
        "next": {"week_start": "2026-09-14", "target_km": 25.0},
    }


def _weeks(series: list[tuple[str, int | None]]) -> dict[str, Any]:
    """Build a minimal ``get_load_trend`` result from (week_start, longest) pairs."""
    return {"weeks": [{"week_start": ws, "longest_run_sec": sec} for ws, sec in series]}


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
