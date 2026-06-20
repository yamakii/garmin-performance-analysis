"""Durability (cardiac-decoupling) API router (read-only).

Thin wrapper over ``GarminDBReader.get_durability_trend`` (Issue #358): all
long-run decoupling/pace-fade computation lives in the reader, so the Web layer
never re-implements the durability logic.
"""

from typing import Any, cast

from fastapi import APIRouter, Request
from garmin_mcp.database.db_reader import GarminDBReader

router = APIRouter(prefix="/api")


@router.get("/durability-trend")
def get_durability_trend_endpoint(
    request: Request,
    start_date: str,
    end_date: str,
    min_distance_km: float = 15.0,
) -> dict[str, Any]:
    """Return the long-run decoupling trend over a date window.

    Read-only: delegates entirely to the reader (no Web-side durability logic).
    ``start_date`` / ``end_date`` are required query parameters (inclusive,
    ``YYYY-MM-DD``); the frontend passes a default window of the trailing N days.
    """
    db_path = getattr(request.app.state, "db_path", None)
    reader = GarminDBReader(db_path=str(db_path) if db_path is not None else None)
    return cast(
        "dict[str, Any]",
        reader.get_durability_trend(start_date, end_date, min_distance_km),
    )
