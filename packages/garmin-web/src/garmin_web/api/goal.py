"""Goal API router (read-only)."""

from fastapi import APIRouter, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.goal import get_goal

router = APIRouter(prefix="/api")


@router.get("/goal")
def get_goal_endpoint(request: Request) -> dict:
    """Return the athlete goal payload (profile + goals + retrospectives).

    Read-only: registration/updates are owned by the CLI (`/set-goal`).
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return get_goal(conn)
