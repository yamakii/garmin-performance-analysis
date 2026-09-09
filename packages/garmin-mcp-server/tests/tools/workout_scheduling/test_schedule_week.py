"""schedule_weekly_prescriptions(): dry run, live registration, status updates, re-registration by recorded id."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    ScheduleWeeklyPrescriptionsParams,
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
    _rest_row,
    _seed,
    _stored,
)


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

    with patch(_CALENDAR, calendar), _offline_garmin():
        result = _schedule_weekly_prescriptions(
            week_reader, ScheduleWeeklyPrescriptionsParams(week_start_date=WEEK_START)
        )

    assert result["dry_run"] is True
    assert result["week_start_date"] == WEEK_START
    assert len(result["items"]) == 2

    by_id = {item["prescription_id"]: item for item in result["items"]}
    assert by_id[easy_id]["existing_same_day"] == ["Tempo"]
    assert by_id[easy_id]["steps"] == [
        {"step_type": "run", "duration_minutes": 45, "hr_high": 150}
    ]
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

    with patch(_CALENDAR, calendar), _offline_garmin():
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


@pytest.mark.unit
def test_schedule_week_reregister_passes_recorded_workout_id(
    week_reader: MagicMock,
) -> None:
    """Re-registering a row hands its recorded workout id to the registration so
    the superseded [MCP] item leaves the calendar (#1042)."""
    from garmin_mcp.database.inserters.plan import update_prescription_status

    (long_id,) = _seed(week_reader, [_long_row()])
    update_prescription_status(
        prescription_id=long_id,
        status="registered",
        garmin_workout_id=333,
        garmin_schedule_id=444,
        db_path=str(week_reader.db_path),
    )

    calendar = MagicMock()
    calendar.return_value.get_scheduled_workouts.return_value = []
    with patch(_CALENDAR, calendar), _offline_garmin():
        planned = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, prescription_ids=[long_id]
            ),
        )

    assert planned["items"][0]["would_replace_workout_id"] == 333

    client = _garmin_client()
    register = MagicMock(
        return_value={
            "workout_id": 1001,
            "schedule_id": 2001,
            "date": "2026-09-13",
            "title": "[MCP] ロング 22km (Z2上限150)",
            "replaced_workout_ids": [333],
            "skipped_replace_ids": [],
        }
    )

    with (
        patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client),
        patch(f"{_MODULE}._register_workout", register),
    ):
        live = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START,
                prescription_ids=[long_id],
                dry_run=False,
            ),
        )

    assert register.call_args.kwargs["replace_workout_id"] == 333
    assert live["registered"][0]["replaced_workout_ids"] == [333]


@pytest.mark.unit
def test_schedule_week_default_path_never_replaces_by_id(
    week_reader: MagicMock,
) -> None:
    """Rows registered on the default (all rows) path carry no recorded id, so
    the id-based delete never fires there."""
    _seed(week_reader, [_long_row(), _easy_row()])
    client = _garmin_client()

    with patch("garmin_mcp.ingest.api_client.get_garmin_client", return_value=client):
        result = _schedule_weekly_prescriptions(
            week_reader,
            ScheduleWeeklyPrescriptionsParams(
                week_start_date=WEEK_START, dry_run=False
            ),
        )

    assert len(result["registered"]) == 2
    client.delete_workout.assert_not_called()
    assert all(r["skipped_replace_ids"] == [] for r in result["registered"])
