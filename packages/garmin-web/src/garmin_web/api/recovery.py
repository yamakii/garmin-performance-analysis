"""Recovery / body-composition API router (read-only, Issue #502).

Wraps ``GarminDBReader`` (#499/#500/#501) via ``queries.recovery``: all RHR/HRV
recovery and body-composition decomposition logic lives in the reader, so the
Web layer stays a thin pass-through.
"""

from typing import Any

from fastapi import APIRouter, Request

from garmin_web.queries import recovery as recovery_queries

router = APIRouter(prefix="/api")


def _db_path(request: Request) -> Any:
    return getattr(request.app.state, "db_path", None)


@router.get("/recovery-trend")
def get_recovery_trend_endpoint(request: Request, weeks: int = 8) -> dict[str, Any]:
    """RHR / HRV recovery trend over the trailing ``weeks`` weeks (#499).

    Read-only: delegates entirely to the reader. ``series`` is date-ascending;
    ``rhr`` / ``hrv`` summary fields are null-safe when data is missing.
    """
    return recovery_queries.get_recovery_trend(_db_path(request), weeks)


@router.get("/recovery-status")
def get_recovery_status_endpoint(
    request: Request, date: str | None = None
) -> dict[str, Any]:
    """Morning go/no-go recovery status for ``date`` (#500).

    ``date`` defaults to the latest day in ``daily_wellness``. A device-off day
    returns ``recommendation="unknown"`` with a "go by feel" reason.
    """
    return recovery_queries.get_recovery_status(_db_path(request), date)


@router.get("/body-composition-trend")
def get_body_composition_trend_endpoint(
    request: Request, weeks: int = 12
) -> dict[str, Any]:
    """Body-composition trend over the trailing ``weeks`` weeks (#501).

    Read-only: ``series`` is date-ascending with fat/lean decomposition, and
    ``change`` carries the first-to-last weight delta breakdown.
    """
    return recovery_queries.get_body_composition_trend(_db_path(request), weeks)
