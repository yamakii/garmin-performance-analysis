"""Activities API router."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.activities import list_activities

router = APIRouter(prefix="/api")


@router.get("/activities")
def get_activities(
    request: Request,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[dict]:
    """Return activities sorted by date descending.

    Query params `from` / `to` are inclusive YYYY-MM-DD bounds.
    Invalid date formats are rejected with 422 by FastAPI validation.
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return list_activities(
            conn,
            from_date=str(from_date) if from_date is not None else None,
            to_date=str(to_date) if to_date is not None else None,
        )
