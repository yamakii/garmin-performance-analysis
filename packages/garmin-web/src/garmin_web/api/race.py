"""Race readiness API router (read-only).

Thin wrapper over ``GarminDBReader.get_race_readiness`` (Issue #356): all VDOT
prediction and goal-gap logic lives in the reader, so the Web layer never
re-implements it.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request
from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_reader import GarminDBReader

router = APIRouter(prefix="/api")


def _db_path(request: Request) -> Any:
    return getattr(request.app.state, "db_path", None)


@router.get("/race-readiness")
def get_race_readiness_endpoint(
    request: Request,
    user_id: str = "default",
    lookback_weeks: int = 8,
) -> dict[str, Any]:
    """Return current VDOT, race-time predictions, and goal progress.

    Read-only: delegates entirely to the reader (no Web-side VDOT logic).
    """
    db_path = getattr(request.app.state, "db_path", None)
    reader = GarminDBReader(db_path=str(db_path) if db_path is not None else None)
    # Bind to a typed local so the reader's (mypy-untyped) Any result narrows
    # to the declared return type without leaking `Any`.
    readiness: dict[str, Any] = reader.get_race_readiness(
        user_id=user_id, lookback_weeks=lookback_weeks
    )
    return readiness


@router.get("/race-prediction-history")
def get_race_prediction_history_endpoint(
    request: Request,
    user_id: str = "default",
    days: Annotated[int, Query(ge=30, le=3650)] = 365,
) -> dict[str, Any]:
    """Return the dated race-time prediction series for the active goal race.

    Read-only: the derivation (objective VDOT curve -> predicted goal time, or
    the Garmin VO2max fallback) lives entirely in the reader. ``days`` bounds
    the series to a trailing window (the full curve runs back to the athlete's
    first logged run).
    """
    with get_connection(_db_path(request)) as conn:
        return cast(
            "dict[str, Any]",
            GarminDBReader.from_connection(conn).get_race_prediction_history(
                user_id, days
            ),
        )
