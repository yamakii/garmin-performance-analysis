"""Trends API router."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries import trends as trends_queries

router = APIRouter(prefix="/api/trends")


def _db_path(request: Request):
    return getattr(request.app.state, "db_path", None)


@router.get("/volume")
def get_volume(
    request: Request,
    granularity: Annotated[Literal["week", "month"], Query()] = "week",
) -> list[dict]:
    """Running volume aggregated per ISO week or calendar month.

    Invalid granularity values are rejected with 422 by FastAPI validation.
    """
    with get_connection(_db_path(request)) as conn:
        return trends_queries.get_volume_trend(conn, granularity=granularity)


@router.get("/physiology")
def get_physiology(request: Request) -> dict:
    """VO2max and lactate threshold time series."""
    with get_connection(_db_path(request)) as conn:
        return trends_queries.get_physiology_trend(conn)


@router.get("/form")
def get_form(request: Request) -> list[dict]:
    """Form evaluation score trend."""
    with get_connection(_db_path(request)) as conn:
        return trends_queries.get_form_trend(conn)


@router.get("/efficiency")
def get_efficiency(request: Request) -> list[dict]:
    """HR efficiency trend with zone distribution."""
    with get_connection(_db_path(request)) as conn:
        return trends_queries.get_efficiency_trend(conn)


@router.get("/heat-adjusted")
def get_heat_adjusted(
    request: Request,
    days: Annotated[int, Query(ge=30, le=1825)] = 365,
) -> dict:
    """Climate-neutral HR-at-pace trend with per-run heat_cost.

    Covers the trailing ``days`` window (default one year). ``days`` outside
    [30, 1825] is rejected with 422 by FastAPI validation.
    """
    end = date.today()
    start = end - timedelta(days=days)
    with get_connection(_db_path(request)) as conn:
        return trends_queries.get_heat_adjusted_trend(
            conn, start.isoformat(), end.isoformat()
        )
