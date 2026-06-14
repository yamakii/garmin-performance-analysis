"""Weekly review API router (read-only)."""

from fastapi import APIRouter, HTTPException, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.weekly_reviews import get_weekly_review, list_weekly_reviews

router = APIRouter(prefix="/api")


@router.get("/weekly-reviews")
def list_weekly_reviews_endpoint(request: Request, limit: int = 12) -> list[dict]:
    """Return recent weekly reviews (newest first).

    Read-only: registration/updates are owned by the CLI (`/weekly-review`).
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        return list_weekly_reviews(conn, limit=limit)


@router.get("/weekly-reviews/{week_start_date}")
def get_weekly_review_endpoint(request: Request, week_start_date: str) -> dict:
    """Return a single weekly review by its week-start date.

    Raises 404 when no review exists for the given week.
    """
    db_path = getattr(request.app.state, "db_path", None)
    with get_connection(db_path) as conn:
        review = get_weekly_review(conn, week_start_date)
    if review is None:
        raise HTTPException(status_code=404, detail="Weekly review not found")
    return review
