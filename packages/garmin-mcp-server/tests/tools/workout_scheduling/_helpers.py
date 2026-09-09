"""Shared helpers for the workout_scheduling tests (split from test_workout_scheduling.py, #1069)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

_MODULE = "garmin_mcp.tools.workout_scheduling"


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


WEEK_START = "2026-09-07"


_CALENDAR = "garmin_mcp.fitness.garmin_calendar.GarminCalendarReader"


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


def _offline_garmin(client: MagicMock | None = None) -> Any:
    """Patch the client factory so a dry run never logs in to Garmin.

    The dry run previews the cleanup the live run would perform first (#1065),
    which needs a client even though it writes nothing.
    """
    return patch(
        "garmin_mcp.ingest.api_client.get_garmin_client",
        return_value=client if client is not None else _garmin_client(),
    )


def _page(start: int, count: int, *, mcp_at: int | None = None) -> list[dict[str, Any]]:
    """A library page of ``count`` workouts, ids ``start..start+count-1``."""
    page: list[dict[str, Any]] = []
    for offset in range(count):
        workout_id = start + offset
        name = (
            "[MCP] Long 120min"
            if mcp_at is not None and workout_id == mcp_at
            else f"Coach {workout_id}"
        )
        page.append({"workoutId": workout_id, "workoutName": name})
    return page


def _past_assignment(schedule_id: int = 9, workout_id: int = 88) -> dict[str, Any]:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return {
        "schedule_id": schedule_id,
        "workout_id": workout_id,
        "date": yesterday,
        "title": "[MCP] 先週のロング",
    }
