"""Unit tests for the custom-workout scheduling tools (issue #851).

The JSON assembly (``build_workout_json``) is pure and tested exhaustively. The
live-write orchestration (delete -> recreate, past-only unschedule, dry-run) goes
through a mocked Garmin client so CI never writes to Garmin.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    CleanupGeneratedWorkoutsParams,
    ScheduleCustomWorkoutParams,
    _cleanup_generated_workouts,
    _collect_mcp_assignments,
    _schedule_custom_workout,
    _target_fields,
    build_workout_json,
)

_MODULE = "garmin_mcp.tools.workout_scheduling"


# ----------------------------------------------------------------------------
# build_workout_json (pure)
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_build_workout_json_single_step_hr_range() -> None:
    """A single 120-min run with a 130-152 bpm range yields a time end-condition
    of 7200s and targetValueOne/Two = 130/152."""
    result = build_workout_json(
        "Long 120min",
        [{"step_type": "run", "duration_minutes": 120, "hr_low": 130, "hr_high": 152}],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["endCondition"]["conditionTypeKey"] == "time"
    assert step["endConditionValue"] == 7200
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["targetValueOne"] == 130
    assert step["targetValueTwo"] == 152


@pytest.mark.unit
def test_build_workout_json_warmup_work_cooldown() -> None:
    """A warmup/run/cooldown trio gets stepOrder 1,2,3 with the right stepTypes."""
    result = build_workout_json(
        "Threshold",
        [
            {"step_type": "warmup", "duration_minutes": 15},
            {"step_type": "run", "duration_minutes": 20, "hr_low": 153, "hr_high": 165},
            {"step_type": "cooldown", "duration_minutes": 10},
        ],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    assert [s["stepOrder"] for s in steps] == [1, 2, 3]
    assert [s["stepType"]["stepTypeKey"] for s in steps] == [
        "warmup",
        "interval",
        "cooldown",
    ]


@pytest.mark.unit
def test_build_workout_json_repeat_group() -> None:
    """A repeat_count=6 group becomes a RepeatGroupDTO with 6 iterations and 2
    child steps."""
    result = build_workout_json(
        "Strides",
        [
            {"step_type": "warmup", "duration_minutes": 10},
            {
                "repeat_count": 6,
                "steps": [
                    {"step_type": "run", "distance_m": 100},
                    {"step_type": "recovery", "duration_seconds": 60},
                ],
            },
            {"step_type": "cooldown", "duration_minutes": 10},
        ],
    )

    steps = result["workoutSegments"][0]["workoutSteps"]
    group = steps[1]
    assert group["type"] == "RepeatGroupDTO"
    assert group["numberOfIterations"] == 6
    assert group["endConditionValue"] == 6.0
    assert len(group["workoutSteps"]) == 2
    assert group["workoutSteps"][0]["stepType"]["stepTypeKey"] == "interval"
    assert group["workoutSteps"][1]["stepType"]["stepTypeKey"] == "recovery"


@pytest.mark.unit
def test_build_workout_json_distance_step() -> None:
    """A distance_m step yields a distance end-condition of 100."""
    result = build_workout_json(
        "Repeat",
        [{"step_type": "run", "distance_m": 100}],
    )

    step = result["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["endConditionValue"] == 100


@pytest.mark.unit
def test_title_prefix_enforced() -> None:
    """The workoutName is force-prefixed with '[MCP] ' without doubling it."""
    plain = build_workout_json("Long 120min", [{"step_type": "run", "distance_m": 1}])
    assert plain["workoutName"] == "[MCP] Long 120min"

    already = build_workout_json(
        "[MCP] Long 120min", [{"step_type": "run", "distance_m": 1}]
    )
    assert already["workoutName"] == "[MCP] Long 120min"


# ----------------------------------------------------------------------------
# _target_fields (ceiling-only HR prescriptions, #979)
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_target_fields_hr_high_only_defaults_floor() -> None:
    """A ceiling-only step still gets an HR-range target, with a non-alerting
    floor of 80 bpm so the low-HR alert can never push the pace up."""
    fields = _target_fields({"hr_high": 150})

    assert fields["targetType"]["workoutTargetTypeId"] == 4
    assert fields["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert fields["targetValueOne"] == 80
    assert fields["targetValueTwo"] == 150


@pytest.mark.unit
def test_target_fields_both_bounds_unchanged() -> None:
    """An explicit floor (quality sessions) is passed through untouched."""
    fields = _target_fields({"hr_low": 162, "hr_high": 169})

    assert fields["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert fields["targetValueOne"] == 162
    assert fields["targetValueTwo"] == 169


@pytest.mark.unit
def test_target_fields_hr_low_only_is_no_target() -> None:
    """A floor without a ceiling carries no target (unchanged behaviour)."""
    fields = _target_fields({"hr_low": 130})

    assert fields["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "targetValueOne" not in fields
    assert "targetValueTwo" not in fields


@pytest.mark.unit
def test_build_workout_json_long_run_ceiling_only_has_hr_target_on_body_step() -> None:
    """A ceiling-governed long run uploads with an 80-150 bpm target on the body
    step, while the untargeted warmup/cooldown stay on no.target."""
    result = build_workout_json(
        "Long 120min (Z2 ceiling 150)",
        [
            {"step_type": "warmup", "duration_minutes": 10},
            {"step_type": "run", "duration_minutes": 120, "hr_high": 150},
            {"step_type": "cooldown", "duration_minutes": 5},
        ],
    )

    warmup, body, cooldown = result["workoutSegments"][0]["workoutSteps"]
    assert body["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert body["targetValueOne"] == 80
    assert body["targetValueTwo"] == 150
    assert warmup["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert cooldown["targetType"]["workoutTargetTypeKey"] == "no.target"


# ----------------------------------------------------------------------------
# schedule_custom_workout (mocked client)
# ----------------------------------------------------------------------------


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

    with patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client):
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


# ----------------------------------------------------------------------------
# cleanup_generated_workouts (mocked client)
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# _collect_mcp_assignments de-duplication (#880)
# ----------------------------------------------------------------------------


def _payload(*items: dict) -> dict:
    return {"calendarItems": list(items)}


def _mcp_item(schedule_id, workout_id, day: str, title: str = "[MCP] Long") -> dict:
    return {
        "itemType": "workout",
        "id": schedule_id,
        "workoutId": workout_id,
        "date": day,
        "title": title,
    }


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


# ----------------------------------------------------------------------------
# cleanup error isolation (#880)
# ----------------------------------------------------------------------------


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
