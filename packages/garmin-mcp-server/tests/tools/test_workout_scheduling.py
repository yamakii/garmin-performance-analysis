"""Unit tests for the custom-workout scheduling tools (issues #851, #981).

The JSON assembly (``build_workout_json``) and the prescription -> steps mapping
(``build_steps_from_prescription``) are pure and tested exhaustively. The
live-write orchestration (delete -> recreate, past-only unschedule, dry-run,
weekly batch) goes through a mocked Garmin client so CI never writes to Garmin;
the weekly batch reads/writes a throwaway DuckDB copy.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    CleanupGeneratedWorkoutsParams,
    ScheduleCustomWorkoutParams,
    ScheduleWeeklyPrescriptionsParams,
    _cleanup_generated_workouts,
    _collect_mcp_assignments,
    _schedule_custom_workout,
    _schedule_weekly_prescriptions,
    _target_fields,
    build_steps_from_prescription,
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


# ----------------------------------------------------------------------------
# build_steps_from_prescription (pure, #981)
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_build_steps_long_km_ceiling_only() -> None:
    """A distance-prescribed long run becomes warmup / body / cooldown with a
    ceiling-only HR target on the body step."""
    steps = build_steps_from_prescription(
        {"session_type": "long", "target_km": 22.0, "hr_high": 150}
    )

    assert len(steps) == 3
    warmup, body, cooldown = steps
    assert warmup == {"step_type": "warmup", "duration_minutes": 10}
    assert cooldown == {"step_type": "cooldown", "duration_minutes": 5}
    assert body["distance_m"] == 22000
    assert body["hr_high"] == 150
    assert "hr_low" not in body


@pytest.mark.unit
def test_build_steps_easy_minutes() -> None:
    """A time-prescribed easy run ends its body step on duration, not distance."""
    steps = build_steps_from_prescription(
        {"session_type": "easy", "target_minutes": 45, "hr_high": 150}
    )

    body = steps[1]
    assert body["duration_minutes"] == 45
    assert "distance_m" not in body
    assert body["hr_high"] == 150


@pytest.mark.unit
def test_build_steps_threshold_both_bounds() -> None:
    """A quality session keeps its prescribed floor as well as its ceiling."""
    steps = build_steps_from_prescription(
        {
            "session_type": "threshold",
            "target_minutes": 20,
            "hr_low": 162,
            "hr_high": 169,
        }
    )

    body = steps[1]
    assert body["hr_low"] == 162
    assert body["hr_high"] == 169


@pytest.mark.unit
def test_build_steps_strides_repeat_group() -> None:
    """Strides need no target: they become a 5x(20s / 90s) repeat group."""
    steps = build_steps_from_prescription({"session_type": "strides"})

    group = steps[1]
    assert group["repeat_count"] == 5
    assert group["steps"] == [
        {"step_type": "run", "duration_seconds": 20},
        {"step_type": "recovery", "duration_seconds": 90},
    ]


@pytest.mark.unit
def test_build_steps_rejects_rest() -> None:
    """A rest day is prescribed but never registered as a run."""
    with pytest.raises(ValueError, match="not registrable"):
        build_steps_from_prescription({"session_type": "rest"})


@pytest.mark.unit
def test_build_steps_rejects_no_target() -> None:
    """A run without any target cannot become a workout."""
    with pytest.raises(ValueError, match="target_minutes or target_km"):
        build_steps_from_prescription({"session_type": "easy"})


# ----------------------------------------------------------------------------
# schedule_weekly_prescriptions (mocked client + throwaway DuckDB, #981)
# ----------------------------------------------------------------------------

WEEK_START = "2026-09-07"
_CALENDAR = "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader"


@pytest.fixture(scope="module")
def _week_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full schema pre-initialized."""
    from garmin_mcp.database.db_writer import GarminDBWriter

    db_path = tmp_path_factory.mktemp("week_schedule_template") / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return Path(db_path)


@pytest.fixture
def week_reader(_week_db_template: Path, tmp_path: Path) -> MagicMock:
    """A stand-in GarminDBReader whose db_path points at a fresh schema copy."""
    dest = tmp_path / "week_schedule.duckdb"
    shutil.copy2(str(_week_db_template), str(dest))
    mock = MagicMock()
    mock.db_path = dest
    return mock


def _seed(reader: MagicMock, rows: list[dict[str, Any]]) -> list[int]:
    """Save one batch of prescriptions and return their ids (reader order)."""
    from garmin_mcp.database.inserters.plan import insert_weekly_prescriptions

    saved = insert_weekly_prescriptions(
        week_start_date=WEEK_START,
        prescriptions=rows,
        db_path=str(reader.db_path),
    )
    return list(saved["prescription_ids"])


def _stored(reader: MagicMock) -> dict[int, dict[str, Any]]:
    """Read the week's canonical rows back, keyed by prescription_id."""
    from garmin_mcp.database.readers.plan import PlanReader

    rows = PlanReader(db_path=str(reader.db_path)).get_weekly_prescriptions(WEEK_START)
    return {row["prescription_id"]: row for row in rows}


def _long_row() -> dict[str, Any]:
    return {
        "date": "2026-09-13",
        "session_type": "long",
        "title": "ロング 22km (Z2上限150)",
        "target_km": 22.0,
        "hr_high": 150,
    }


def _easy_row() -> dict[str, Any]:
    return {
        "date": "2026-09-09",
        "session_type": "easy",
        "title": "イージー 45分",
        "target_minutes": 45,
        "hr_high": 150,
    }


def _rest_row() -> dict[str, Any]:
    return {"date": "2026-09-11", "session_type": "rest", "title": "休養"}


def _garmin_client(schedule_id: int = 2001, workout_id: int = 1001) -> MagicMock:
    client = MagicMock()
    client.get_workouts.return_value = []
    client.upload_workout.return_value = {"workoutId": workout_id}
    client.schedule_workout.return_value = {"workoutScheduleId": schedule_id}
    return client


@pytest.mark.unit
def test_schedule_week_dry_run_lists_items_and_conflicts(
    week_reader: MagicMock,
) -> None:
    """The dry run plans every registrable row, skips rest and reports the
    non-[MCP] Garmin items already sitting on those days."""
    ids = _seed(week_reader, [_long_row(), _easy_row(), _rest_row()])
    long_id, easy_id, rest_id = ids[0], ids[1], ids[2]

    calendar = MagicMock()
    calendar.return_value.get_scheduled_workouts.return_value = [
        {"date": "2026-09-09", "title": "Tempo"},
        {"date": "2026-09-13", "title": "[MCP] 先週のロング"},
    ]

    with patch(_CALENDAR, calendar):
        result = _schedule_weekly_prescriptions(
            week_reader, ScheduleWeeklyPrescriptionsParams(week_start_date=WEEK_START)
        )

    assert result["dry_run"] is True
    assert result["week_start_date"] == WEEK_START
    assert len(result["items"]) == 2

    by_id = {item["prescription_id"]: item for item in result["items"]}
    assert by_id[easy_id]["existing_same_day"] == ["Tempo"]
    assert by_id[easy_id]["steps"][1]["duration_minutes"] == 45
    # The same-title [MCP] template is replaced automatically, so it is not a
    # conflict the user has to resolve.
    assert by_id[long_id]["existing_same_day"] == []
    assert by_id[long_id]["already_registered"] is False

    assert [s["prescription_id"] for s in result["skipped"]] == [rest_id]
    assert "not registrable" in result["skipped"][0]["reason"]


@pytest.mark.unit
def test_schedule_week_live_registers_and_updates_status(
    week_reader: MagicMock,
) -> None:
    """A live batch registers every item and records the ids on its row."""
    ids = _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()

    with patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    assert result["dry_run"] is False
    assert len(result["registered"]) == 2
    assert result["failed"] == []
    assert {r["schedule_id"] for r in result["registered"]} == {2001}
    assert all(r["title"].startswith("[MCP] ") for r in result["registered"])

    stored = _stored(week_reader)
    for prescription_id in ids:
        row = stored[prescription_id]
        assert row["status"] == "registered"
        assert row["garmin_workout_id"] == 1001
        assert row["garmin_schedule_id"] == 2001


@pytest.mark.unit
def test_schedule_week_isolates_failures(week_reader: MagicMock) -> None:
    """One failing upload never aborts the batch or the rows already written."""
    ids = _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()
    # Reader order is by date: the easy run (09-09) is registered first.
    easy_id, long_id = ids[1], ids[0]
    client.upload_workout.side_effect = [
        {"workoutId": 1001},
        Exception("API Error 429 - Too Many Requests"),
    ]

    with patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    assert [r["prescription_id"] for r in result["registered"]] == [easy_id]
    assert [f["prescription_id"] for f in result["failed"]] == [long_id]
    assert "429" in result["failed"][0]["error"]

    stored = _stored(week_reader)
    assert stored[easy_id]["status"] == "registered"
    assert stored[long_id]["status"] == "prescribed"
    assert stored[long_id]["garmin_schedule_id"] is None


@pytest.mark.unit
def test_schedule_week_skips_already_registered_unless_explicit(
    week_reader: MagicMock,
) -> None:
    """An already-registered row is left alone unless its id is named."""
    from garmin_mcp.database.inserters.plan import update_prescription_status

    (long_id,) = _seed(week_reader, [_long_row()])
    update_prescription_status(
        prescription_id=long_id,
        status="registered",
        garmin_workout_id=111,
        garmin_schedule_id=222,
        db_path=str(week_reader.db_path),
    )

    calendar = MagicMock()
    calendar.return_value.get_scheduled_workouts.return_value = []

    with patch(_CALENDAR, calendar):
        default = _schedule_weekly_prescriptions(
            week_reader, ScheduleWeeklyPrescriptionsParams(week_start_date=WEEK_START)
        )
        explicit = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, prescription_ids=[long_id]
            ),
        )

    assert default["items"] == []
    assert [s["prescription_id"] for s in default["skipped"]] == [long_id]
    assert "already registered" in default["skipped"][0]["reason"]

    assert explicit["skipped"] == []
    assert [item["prescription_id"] for item in explicit["items"]] == [long_id]
    assert explicit["items"][0]["already_registered"] is True
