"""Planned-workout API router (read-only, Issue #721).

Serves the Today dashboard's "今日の予定" card. Delegates to
``queries.planned``; the Web layer stays a thin pass-through. Plan generation
is owned by the CLI (`/plan-training`).
"""

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.planned import get_planned_workout_for_date

router = APIRouter(prefix="/api")


@router.get("/planned-workouts/today")
def get_planned_workout_today_endpoint(
    request: Request, date: str | None = None
) -> dict[str, Any] | None:
    """Return the planned workout for ``date`` (defaults to today).

    ``date`` (``YYYY-MM-DD``) selects the day; when omitted the server's local
    date is used. Returns ``null`` (status 200) when nothing is planned for the
    day — a rest day is a normal, non-error state.
    """
    target_date = date if date is not None else _dt.date.today().isoformat()
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return get_planned_workout_for_date(conn, target_date)
