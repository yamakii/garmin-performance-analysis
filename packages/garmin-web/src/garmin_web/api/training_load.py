"""Training-load (ACWR) API router (read-only).

Thin wrapper over ``GarminDBReader.get_acwr`` / ``get_load_trend`` (Issue #357):
all ACWR computation lives in the reader, so the Web layer never re-implements
the injury-risk logic.
"""

from typing import Any

from fastapi import APIRouter, Request
from garmin_mcp.database.db_reader import GarminDBReader

router = APIRouter(prefix="/api")


@router.get("/training-load")
def get_training_load_endpoint(
    request: Request,
    lookback_weeks: int = 12,
) -> dict[str, Any]:
    """Return the current ACWR snapshot plus the weekly load/ACWR trend.

    Read-only: delegates entirely to the reader (no Web-side ACWR logic).
    """
    db_path = getattr(request.app.state, "db_path", None)
    reader = GarminDBReader(db_path=str(db_path) if db_path is not None else None)
    current: dict[str, Any] = reader.get_acwr()
    trend: dict[str, Any] = reader.get_load_trend(lookback_weeks)
    return {"current": current, "trend": trend}
