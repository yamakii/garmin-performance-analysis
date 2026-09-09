"""Workout-library paging and pre-registration cleanup; schedule_custom_workout / cleanup_generated_workouts delegation."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    CleanupGeneratedWorkoutsParams,
    ScheduleCustomWorkoutParams,
    ScheduleWeeklyPrescriptionsParams,
    _cleanup_generated_workouts,
    _fetch_library,
    _register_workout,
    _schedule_custom_workout,
    _schedule_weekly_prescriptions,
)
from tests.tools.workout_scheduling._helpers import (
    _CALENDAR,
    _MODULE,
    WEEK_START,
    _easy_row,
    _garmin_client,
    _long_row,
    _offline_garmin,
    _page,
    _past_assignment,
    _seed,
)


@pytest.mark.unit
def test_fetch_library_pages_until_short_page() -> None:
    """A full first page is followed by another request; a short page ends it."""
    client = MagicMock()
    client.get_workouts.side_effect = [_page(0, 100), _page(100, 40)]

    library = _fetch_library(client)

    assert len(library) == 140
    assert [c.args for c in client.get_workouts.call_args_list] == [
        (0, 100),
        (100, 100),
    ]


@pytest.mark.unit
def test_fetch_library_single_short_page() -> None:
    """A library smaller than one page costs exactly one request."""
    client = MagicMock()
    client.get_workouts.side_effect = [_page(0, 5)]

    library = _fetch_library(client)

    assert len(library) == 5
    assert [c.args for c in client.get_workouts.call_args_list] == [(0, 100)]


@pytest.mark.unit
def test_register_workout_replaces_same_title_beyond_first_page() -> None:
    """A same-title [MCP] template past position 100 is still replaced (#1065)."""
    client = MagicMock()
    client.get_workouts.side_effect = [_page(0, 100), _page(100, 40, mcp_at=120)]
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}

    result = _register_workout(
        client,
        on_date="2026-09-13",
        title="Long 120min",
        steps=[{"step_type": "run", "duration_minutes": 120}],
    )

    client.delete_workout.assert_called_once_with(120)
    assert result["replaced_workout_ids"] == [120]


@pytest.mark.unit
def test_schedule_week_live_cleans_up_before_registration(
    week_reader: MagicMock,
) -> None:
    """The live batch tidies stale [MCP] items before it uploads anything."""
    _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 77},
    ]

    with (
        _offline_garmin(client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[_past_assignment()]),
    ):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    client.unschedule_workout.assert_called_once_with(9)
    client.delete_workout.assert_called_once_with(77)
    calls = [c[0] for c in client.method_calls]
    assert calls.index("unschedule_workout") < calls.index("upload_workout")
    assert calls.index("delete_workout") < calls.index("upload_workout")

    assert result["cleanup"]["unscheduled_schedule_ids"] == [9]
    assert result["cleanup"]["deleted_workout_ids"] == [77]
    assert len(result["registered"]) == 2


@pytest.mark.unit
def test_schedule_week_dry_run_reports_would_cleanup_without_writes(
    week_reader: MagicMock,
) -> None:
    """The dry run reports the tidy the live run would perform, writing nothing."""
    _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 77},
    ]
    calendar = MagicMock()
    calendar.return_value.get_scheduled_workouts.return_value = []

    with (
        patch(_CALENDAR, calendar),
        _offline_garmin(client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[_past_assignment()]),
    ):
        result = _schedule_weekly_prescriptions(
            week_reader, ScheduleWeeklyPrescriptionsParams(week_start_date=WEEK_START)
        )

    assert result["dry_run"] is True
    assert [a["schedule_id"] for a in result["would_cleanup"]["would_unschedule"]] == [
        9
    ]
    assert result["would_cleanup"]["would_delete"] == [
        {"workout_id": 77, "title": "[MCP] Orphan"}
    ]
    client.unschedule_workout.assert_not_called()
    client.delete_workout.assert_not_called()
    client.upload_workout.assert_not_called()


@pytest.mark.unit
def test_schedule_week_cleanup_failure_does_not_abort_registration(
    week_reader: MagicMock,
) -> None:
    """A failing cleanup deletion is reported, never fatal to the batch."""
    _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 77},
    ]
    client.delete_workout.side_effect = Exception("API Error 404 - Not Found")

    with (
        _offline_garmin(client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[]),
    ):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    assert len(result["registered"]) == 2
    assert result["failed"] == []
    assert result["cleanup"]["deleted_workout_ids"] == []
    assert result["cleanup"]["failed_delete"] == [
        {"workout_id": 77, "error": "API Error 404 - Not Found"}
    ]


@pytest.mark.unit
def test_schedule_week_cleanup_keeps_today_and_future(week_reader: MagicMock) -> None:
    """Today's and next week's [MCP] items survive the pre-registration tidy."""
    _seed(week_reader, [_long_row()])
    client = _garmin_client()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] 今日のイージー", "workoutId": 55},
        {"workoutName": "[MCP] 来週のロング", "workoutId": 66},
    ]
    assignments = [
        {
            "schedule_id": 1,
            "workout_id": 55,
            "date": date.today().isoformat(),
            "title": "[MCP] 今日のイージー",
        },
        {
            "schedule_id": 2,
            "workout_id": 66,
            "date": (date.today() + timedelta(days=7)).isoformat(),
            "title": "[MCP] 来週のロング",
        },
    ]

    with (
        _offline_garmin(client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=assignments),
    ):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    client.unschedule_workout.assert_not_called()
    client.delete_workout.assert_not_called()
    assert result["cleanup"]["unscheduled_schedule_ids"] == []
    assert result["cleanup"]["deleted_workout_ids"] == []


@pytest.mark.unit
def test_schedule_custom_workout_cleans_up_first() -> None:
    """A single-session registration tidies stale [MCP] items before uploading."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 77},
    ]
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}

    with (
        _offline_garmin(client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[_past_assignment()]),
    ):
        result = _schedule_custom_workout(
            MagicMock(),
            ScheduleCustomWorkoutParams(
                date="2026-09-13",
                title="ロング 22km",
                steps=[{"step_type": "run", "duration_minutes": 120}],
            ),
        )

    client.unschedule_workout.assert_called_once_with(9)
    client.delete_workout.assert_called_once_with(77)
    calls = [c[0] for c in client.method_calls]
    assert calls.index("unschedule_workout") < calls.index("upload_workout")
    assert calls.index("delete_workout") < calls.index("upload_workout")

    assert result["workout_id"] == 999
    assert result["cleanup"]["unscheduled_schedule_ids"] == [9]
    assert result["cleanup"]["deleted_workout_ids"] == [77]


@pytest.mark.unit
def test_cleanup_generated_workouts_delegates_to_runner() -> None:
    """The manual tool returns the shared runner's result; dry runs never call it."""
    client = MagicMock()
    outcome = {
        "unscheduled_schedule_ids": [1],
        "deleted_workout_ids": [10],
        "failed_unschedule": [],
        "failed_delete": [],
    }
    runner = MagicMock(return_value=outcome)

    with _offline_garmin(client), patch(f"{_MODULE}._run_cleanup", runner):
        live = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    assert live == {"dry_run": False, **outcome}
    assert runner.call_args.args[0] is client

    runner.reset_mock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 10}
    ]
    with (
        _offline_garmin(client),
        patch(f"{_MODULE}._run_cleanup", runner),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[]),
    ):
        dry = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=True)
        )

    runner.assert_not_called()
    client.delete_workout.assert_not_called()
    assert dry["would_delete"] == [{"workout_id": 10, "title": "[MCP] Orphan"}]
