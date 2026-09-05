"""Monthly plan API router (read-only)."""

import datetime as _dt
from typing import Annotated

from fastapi import APIRouter, Query, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.plan import get_month_plan, list_training_blocks

router = APIRouter(prefix="/api")

# Zero-padded YYYY-MM. FastAPI turns a violation into a 422 before the handler
# runs, so "2026-9" never reaches the query.
_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/plan/month")
def get_month_plan_endpoint(
    request: Request,
    month: Annotated[str | None, Query(pattern=_MONTH_PATTERN)] = None,
) -> dict:
    """Return the monthly plan grid: weeks x days, prescriptions vs actuals.

    Query params: ``month`` (``YYYY-MM``, defaults to the current month; a
    malformed value is rejected with 422). Read-only: prescriptions and the
    block ledger are written by the CLI (`/weekly-review`, `/set-training-plan`).
    """
    target_month = month or _dt.date.today().strftime("%Y-%m")
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return get_month_plan(conn, target_month)


@router.get("/plan/blocks")
def list_training_blocks_endpoint(request: Request) -> list[dict]:
    """Return the mesocycle block ledger in display order.

    Read-only: the ledger is written by the CLI (`/set-training-plan`).
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return list_training_blocks(conn)
