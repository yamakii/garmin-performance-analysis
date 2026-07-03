"""Activity detail API router (detail, time-series, track, sections)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.detail import get_activity_detail
from garmin_web.queries.sections import get_sections, list_section_versions
from garmin_web.queries.time_series import get_time_series
from garmin_web.queries.track import get_track

router = APIRouter(prefix="/api")


@router.get("/activities/{activity_id}")
def get_detail(request: Request, activity_id: int) -> dict:
    """Return aggregated detail for one activity, or 404 if unknown."""
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        detail = get_activity_detail(conn, activity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return detail


@router.get("/activities/{activity_id}/time-series")
def get_activity_time_series(
    request: Request,
    activity_id: int,
    metrics: Annotated[str, Query(min_length=1)],
    max_points: Annotated[int, Query(ge=2, le=5000)] = 500,
) -> dict:
    """Return downsampled time series for the requested metrics.

    `metrics` is a required comma-separated list of metric column names.
    Unknown metric names are rejected with 422.
    """
    metric_names = [name.strip() for name in metrics.split(",") if name.strip()]
    db_path = getattr(request.app.state, "db_path", None)
    try:
        with get_connection(db_path) as conn:
            return get_time_series(
                conn, activity_id, metric_names, max_points=max_points
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/activities/{activity_id}/track")
def get_activity_track(request: Request, activity_id: int) -> dict:
    """Return the GPS track for an activity.

    Activities without GPS data (e.g. indoor runs) return 200 with an
    empty points array.
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return {"points": get_track(conn, activity_id)}


@router.get("/activities/{activity_id}/sections/versions")
def get_activity_section_versions(request: Request, activity_id: int) -> list[dict]:
    """Return saved analysis batches for an activity (newest first).

    Returns an empty list (status 200) when the activity has no section
    analyses. The more specific ``/versions`` path is declared before the bare
    ``/sections`` route so it is matched first.
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return list_section_versions(conn, activity_id)


@router.get("/activities/{activity_id}/sections")
def get_activity_sections(
    request: Request,
    activity_id: int,
    created_at: Annotated[str | None, Query()] = None,
) -> dict:
    """Return section analyses keyed by section_type.

    Returns the latest version of each section by default; ``created_at`` pins
    the view to that analysis run (each section's latest version at or before
    the timestamp).
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return get_sections(conn, activity_id, created_at=created_at)
