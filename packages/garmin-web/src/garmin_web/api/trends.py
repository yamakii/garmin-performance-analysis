"""Trends API router."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries import objective_fitness as objective_fitness_queries
from garmin_web.queries import settings as settings_queries
from garmin_web.queries import trends as trends_queries

router = APIRouter(prefix="/api/trends")


def _db_path(request: Request):
    return getattr(request.app.state, "db_path", None)


@router.get("/volume")
def get_volume(
    request: Request,
    granularity: Annotated[Literal["week", "month"], Query()] = "week",
) -> list[dict]:
    """Running volume aggregated per calendar week or calendar month.

    Weekly buckets honor the athlete's configured ``week_start_day``
    (``athlete_profile``; defaults to Monday). Invalid granularity values are
    rejected with 422 by FastAPI validation.
    """
    with get_connection(_db_path(request)) as conn:
        week_start_day = settings_queries.get_week_start_day(conn)
        return trends_queries.get_volume_trend(
            conn, granularity=granularity, week_start_day=week_start_day
        )


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


@router.get("/critical-speed")
def get_critical_speed(request: Request) -> list[dict]:
    """Quarterly threshold-anchored Critical Speed fit (CS pace + R^2).

    D' is intentionally omitted: without short/long max efforts the intercept
    is invalid, so CS is presented only as a lactate-threshold speed proxy.
    """
    with get_connection(_db_path(request)) as conn:
        return objective_fitness_queries.get_quarterly_critical_speed(conn)


@router.get("/narration/versions")
def get_trend_narration_versions_endpoint(
    request: Request,
    granularity: Annotated[Literal["week", "month"], Query()] = "week",
    period_start: str = Query(...),
) -> list[dict]:
    """All saved narration versions for a single period, newest first.

    Declared before ``/narration`` so this fixed path is matched ahead of the
    latest-period route. Invalid granularity values are rejected with 422 by
    FastAPI validation; an unknown period returns ``[]`` (200).
    """
    with get_connection(_db_path(request)) as conn:
        return trends_queries.list_trend_narration_versions(
            conn, granularity, period_start
        )


@router.get("/narration")
def get_trend_narration_endpoint(
    request: Request,
    granularity: Annotated[Literal["week", "month"], Query()] = "week",
) -> dict:
    """Latest-version narration for the most recent period of a granularity.

    Invalid granularity values are rejected with 422 by FastAPI validation. When
    no narration exists yet, responds with 404.
    """
    with get_connection(_db_path(request)) as conn:
        narration = trends_queries.get_trend_narration(conn, granularity)
    if narration is None:
        raise HTTPException(status_code=404, detail="No trend narration found")
    return narration


@router.get("/objective-fitness")
def get_objective_fitness(request: Request) -> dict:
    """Objective (real-run derived) fitness curve vs Garmin VO2max + optimism gap.

    Overlays a rolling 90-day best-effort performance-VDOT curve on Garmin's own
    VO2max series and surfaces the optimism gap (Garmin-derived VDOT minus the
    objective VDOT, in VDOT and s/km).
    """
    with get_connection(_db_path(request)) as conn:
        return objective_fitness_queries.get_objective_fitness_trend(conn)
