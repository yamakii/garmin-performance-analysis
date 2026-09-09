"""Registration replace rules (same title, recorded id), cleanup of past [MCP] workouts, assignment collection, failure isolation."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    CleanupGeneratedWorkoutsParams,
    ScheduleCustomWorkoutParams,
    _cleanup_generated_workouts,
    _collect_mcp_assignments,
    _register_workout,
    _schedule_custom_workout,
)
from tests.tools.workout_scheduling._helpers import _MODULE, _mcp_item, _payload


@pytest.mark.unit
def test_schedule_replaces_same_title_template() -> None:
    """A same-title [MCP] template is deleted before the new one is uploaded."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Long 120min", "workoutId": 111},
        {"workoutName": "Coach Threshold", "workoutId": 222},
    ]
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}
    # The template is still scheduled in the future, so the pre-registration
    # cleanup leaves it to the same-title replacement below.
    scheduled = [
        {
            "schedule_id": 7,
            "workout_id": 111,
            "date": "2099-01-01",
            "title": "[MCP] Long 120min",
        }
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=scheduled),
    ):
        result = _schedule_custom_workout(
            MagicMock(),
            ScheduleCustomWorkoutParams(
                date="2026-07-12",
                title="Long 120min",
                steps=[{"step_type": "run", "duration_minutes": 120}],
            ),
        )

    # delete_workout called for the matching [MCP] template only (not the Coach one).
    client.delete_workout.assert_called_once_with(111)

    # Ordering: delete happens before upload.
    method_calls = [c[0] for c in client.method_calls]
    assert method_calls.index("delete_workout") < method_calls.index("upload_workout")

    assert result["workout_id"] == 999
    assert result["schedule_id"] == 555
    assert result["title"] == "[MCP] Long 120min"
    assert result["replaced_workout_ids"] == [111]


@pytest.mark.unit
def test_schedule_one_replaces_recorded_workout_id_with_new_title() -> None:
    """The workout recorded for a slot is deleted even when the new title
    differs, so the revised item does not sit next to the old one (#1042)."""
    client = MagicMock()
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}

    result = _register_workout(
        client,
        on_date="2026-09-10",
        title="new",
        steps=[{"step_type": "run", "duration_minutes": 25}],
        templates=[{"workoutName": "[MCP] old", "workoutId": 111}],
        replace_workout_id=111,
    )

    client.delete_workout.assert_called_once_with(111)
    method_calls = [c[0] for c in client.method_calls]
    assert method_calls.index("delete_workout") < method_calls.index("upload_workout")

    assert result["replaced_workout_ids"] == [111]
    assert result["skipped_replace_ids"] == []


@pytest.mark.unit
def test_schedule_one_does_not_double_delete_same_title_and_id() -> None:
    """An id that is also the same-title template is deleted exactly once."""
    client = MagicMock()
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}

    result = _register_workout(
        client,
        on_date="2026-09-10",
        title="same",
        steps=[{"step_type": "run", "duration_minutes": 25}],
        templates=[{"workoutName": "[MCP] same", "workoutId": 111}],
        replace_workout_id=111,
    )

    client.delete_workout.assert_called_once_with(111)
    assert result["replaced_workout_ids"] == [111]


@pytest.mark.unit
def test_schedule_one_skips_non_mcp_replace_id() -> None:
    """A recorded id pointing at a manual workout is reported, never deleted."""
    client = MagicMock()
    client.upload_workout.return_value = {"workoutId": 999}
    client.schedule_workout.return_value = {"workoutScheduleId": 555}

    result = _register_workout(
        client,
        on_date="2026-09-10",
        title="new",
        steps=[{"step_type": "run", "duration_minutes": 25}],
        templates=[{"workoutName": "Coach Tempo", "workoutId": 222}],
        replace_workout_id=222,
    )

    client.delete_workout.assert_not_called()
    assert result["replaced_workout_ids"] == []
    assert result["skipped_replace_ids"] == [222]


@pytest.mark.unit
def test_cleanup_unschedules_past_only() -> None:
    """Past-dated [MCP] assignments are unscheduled; future ones are kept."""
    client = MagicMock()
    client.get_workouts.return_value = []
    assignments = [
        {"schedule_id": 1, "workout_id": 10, "date": "2026-07-01", "title": "[MCP] A"},
        {"schedule_id": 2, "workout_id": 20, "date": "2026-07-20", "title": "[MCP] B"},
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=assignments),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    client.unschedule_workout.assert_called_once_with(1)
    assert result["unscheduled_schedule_ids"] == [1]


@pytest.mark.unit
def test_cleanup_ignores_non_prefixed() -> None:
    """Templates without the [MCP] prefix are never deleted; [MCP] ones are."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 10},
        {"workoutName": "Coach Long Run", "workoutId": 20},
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[]),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    client.delete_workout.assert_called_once_with(10)
    assert result["deleted_workout_ids"] == [10]


@pytest.mark.unit
def test_cleanup_dry_run_no_writes() -> None:
    """dry_run=True performs no unschedule/delete and lists the targets."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 10},
    ]
    assignments = [
        {"schedule_id": 1, "workout_id": 99, "date": "2026-07-01", "title": "[MCP] A"},
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=assignments),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=True)
        )

    client.unschedule_workout.assert_not_called()
    client.delete_workout.assert_not_called()
    assert result["dry_run"] is True
    assert len(result["would_unschedule"]) == 1
    assert result["would_delete"] == [{"workout_id": 10, "title": "[MCP] Orphan"}]


@pytest.mark.unit
def test_collect_mcp_assignments_dedupes_duplicate_schedule_ids() -> None:
    """The calendar service repeats items; the same schedule_id is kept once."""
    client = MagicMock()
    client.get_scheduled_workouts.return_value = _payload(
        _mcp_item(1729244755, 1648964877, "2026-08-01"),
        _mcp_item(1729244755, 1648964877, "2026-08-01"),
    )

    assignments = _collect_mcp_assignments(client, window_days=0)

    assert len(assignments) == 1
    assert assignments[0]["schedule_id"] == 1729244755


@pytest.mark.unit
def test_collect_mcp_assignments_keeps_distinct_schedule_ids() -> None:
    """Distinct assignments survive de-duplication, in first-seen order."""
    client = MagicMock()
    client.get_scheduled_workouts.return_value = _payload(
        _mcp_item(1, 10, "2026-08-01"),
        _mcp_item(2, 20, "2026-08-02"),
        _mcp_item(1, 10, "2026-08-01"),
    )

    assignments = _collect_mcp_assignments(client, window_days=0)

    assert [a["schedule_id"] for a in assignments] == [1, 2]


@pytest.mark.unit
def test_collect_mcp_assignments_skips_missing_schedule_id() -> None:
    """An item without an id cannot be unscheduled, so it is dropped."""
    client = MagicMock()
    client.get_scheduled_workouts.return_value = _payload(
        _mcp_item(None, 10, "2026-08-01"),
        _mcp_item(2, 20, "2026-08-02"),
    )

    assignments = _collect_mcp_assignments(client, window_days=0)

    assert [a["schedule_id"] for a in assignments] == [2]


@pytest.mark.unit
def test_cleanup_continues_when_one_unschedule_fails() -> None:
    """A failing unschedule must not abort the remaining template deletions."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 77},
    ]
    client.unschedule_workout.side_effect = [
        Exception("API Error 404 - No workout found for workout schedule = 1"),
        None,
    ]
    assignments = [
        {"schedule_id": 1, "workout_id": 10, "date": "2026-07-01", "title": "[MCP] A"},
        {"schedule_id": 2, "workout_id": 20, "date": "2026-07-02", "title": "[MCP] B"},
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=assignments),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    # The second unschedule still ran, and the template deletion was reached.
    assert result["unscheduled_schedule_ids"] == [2]
    assert result["deleted_workout_ids"] == [77]
    client.delete_workout.assert_called_once_with(77)

    assert len(result["failed_unschedule"]) == 1
    assert result["failed_unschedule"][0]["schedule_id"] == 1
    assert "404" in result["failed_unschedule"][0]["error"]
    assert "error" not in result


@pytest.mark.unit
def test_cleanup_continues_when_one_delete_fails() -> None:
    """A failing template delete is recorded without stopping the others."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] A", "workoutId": 10},
        {"workoutName": "[MCP] B", "workoutId": 20},
    ]
    client.delete_workout.side_effect = [Exception("boom"), None]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=[]),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    assert result["deleted_workout_ids"] == [20]
    assert len(result["failed_delete"]) == 1
    assert result["failed_delete"][0]["workout_id"] == 10
    assert "error" not in result


@pytest.mark.unit
def test_cleanup_reports_empty_failure_lists_on_success() -> None:
    """A fully successful cleanup reports both failure lists as empty."""
    client = MagicMock()
    client.get_workouts.return_value = [
        {"workoutName": "[MCP] Orphan", "workoutId": 10},
    ]
    assignments = [
        {"schedule_id": 1, "workout_id": 99, "date": "2026-07-01", "title": "[MCP] A"},
    ]

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._collect_mcp_assignments", return_value=assignments),
        patch(f"{_MODULE}.date") as date_mock,
    ):
        date_mock.today.return_value = date(2026, 7, 11)
        date_mock.fromisoformat.side_effect = date.fromisoformat
        result = _cleanup_generated_workouts(
            MagicMock(), CleanupGeneratedWorkoutsParams(dry_run=False)
        )

    assert result["unscheduled_schedule_ids"] == [1]
    assert result["deleted_workout_ids"] == [10]
    assert result["failed_unschedule"] == []
    assert result["failed_delete"] == []
