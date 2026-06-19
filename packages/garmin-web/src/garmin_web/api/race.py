"""Race readiness API router (read-only).

Thin wrapper over ``GarminDBReader.get_race_readiness`` (Issue #356): all VDOT
prediction and goal-gap logic lives in the reader, so the Web layer never
re-implements it.
"""

from typing import Any

from fastapi import APIRouter, Request
from garmin_mcp.database.db_reader import GarminDBReader

router = APIRouter(prefix="/api")


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
