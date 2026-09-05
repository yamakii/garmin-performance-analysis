"""Deterministic reconciliation of weekly prescriptions against actual runs.

Adherence must exist without an LLM in the loop, so linking a prescribed
session to what actually happened is pure arithmetic over the ``activities``
table:

- an activity on the prescribed date within tolerance (±15% short / +30% long of
  ``target_km`` and ``target_minutes``) marks the row ``done``;
- an activity outside tolerance — or any activity on a ``rest`` day — marks it
  ``replaced`` (the session happened, just not as prescribed);
- a past date with no activity marks it ``skipped``, except ``rest`` days, where
  doing nothing is exactly compliance (``done``).

Only rows of the latest batch per week and only ``prescribed`` / ``registered``
rows are touched: superseded batches are history, and ``done`` / ``replaced`` /
``skipped`` rows keep whatever a previous run (or a manual update) decided.
Future dates are left alone.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

#: Fraction of the target below which a session no longer counts as done.
TOLERANCE_LOW = 0.85

#: Fraction of the target above which a session no longer counts as done.
TOLERANCE_HIGH = 1.30

#: Statuses that reconciliation is allowed to overwrite.
_OPEN_STATUSES = ("prescribed", "registered")


def _default_db_path() -> str:
    """Resolve the default DuckDB path (never hard-coded by callers)."""
    from garmin_mcp.utils.paths import get_database_dir

    return str(get_database_dir() / "garmin_performance.duckdb")


def _within_tolerance(target: float | None, actual: float | None) -> bool:
    """Return whether ``actual`` sits inside the tolerance band around ``target``.

    A missing target imposes no constraint (``True``); a present target with a
    missing actual value cannot be verified (``False``).
    """
    if target is None:
        return True
    if actual is None:
        return False
    return TOLERANCE_LOW * target <= actual <= TOLERANCE_HIGH * target


def _pick_activity(
    candidates: list[dict[str, Any]],
    target_km: float | None,
    target_minutes: float | None,
) -> dict[str, Any]:
    """Pick the activity that best matches a prescription on a multi-run day.

    Prefers a candidate inside tolerance; otherwise falls back to the longest
    run of the day, which is the one a prescription most plausibly refers to.
    """
    for candidate in candidates:
        if _within_tolerance(target_km, candidate["distance_km"]) and _within_tolerance(
            target_minutes, candidate["duration_min"]
        ):
            return candidate
    return candidates[0]


def reconcile_prescriptions(
    start_date: str,
    end_date: str,
    *,
    user_id: str = "default",
    today: date | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Link open prescriptions in a date range to the runs that happened.

    Args:
        start_date: Inclusive range start (``YYYY-MM-DD``).
        end_date: Inclusive range end (``YYYY-MM-DD``).
        user_id: Ledger owner identifier (defaults to ``"default"``).
        today: Reference date for "past vs future"; defaults to the system date.
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``{"updated": n, "done": n, "replaced": n, "skipped": n}`` counting the
        rows whose status this call changed.
    """
    if db_path is None:
        db_path = _default_db_path()
    if today is None:
        today = date.today()

    from garmin_mcp.database.connection import get_write_connection
    from garmin_mcp.database.readers.plan import PlanReader

    prescriptions = PlanReader(db_path=db_path).list_prescriptions(
        start_date, end_date, user_id=user_id
    )
    open_rows = [p for p in prescriptions if p.get("status") in _OPEN_STATUSES]

    counts = {"updated": 0, "done": 0, "replaced": 0, "skipped": 0}
    if not open_rows:
        return counts

    with get_write_connection(db_path) as conn:
        activity_rows = conn.execute(
            "SELECT activity_id, activity_date, total_distance_km, "
            "total_time_seconds FROM activities "
            "WHERE activity_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) "
            "ORDER BY activity_date, total_distance_km DESC",
            [start_date, end_date],
        ).fetchall()

        by_date: dict[str, list[dict[str, Any]]] = {}
        for activity_id, activity_date, distance_km, time_seconds in activity_rows:
            by_date.setdefault(str(activity_date), []).append(
                {
                    "activity_id": activity_id,
                    "distance_km": distance_km,
                    "duration_min": (
                        time_seconds / 60.0 if time_seconds is not None else None
                    ),
                }
            )

        for row in open_rows:
            row_date = datetime.strptime(str(row["date"]), "%Y-%m-%d").date()
            if row_date >= today:
                continue

            session_type = row.get("session_type")
            candidates = by_date.get(str(row["date"]), [])
            actual_activity_id: int | None = None

            if candidates:
                if session_type == "rest":
                    new_status = "replaced"
                    actual_activity_id = candidates[0]["activity_id"]
                else:
                    match = _pick_activity(
                        candidates, row.get("target_km"), row.get("target_minutes")
                    )
                    actual_activity_id = match["activity_id"]
                    new_status = (
                        "done"
                        if _within_tolerance(row.get("target_km"), match["distance_km"])
                        and _within_tolerance(
                            row.get("target_minutes"), match["duration_min"]
                        )
                        else "replaced"
                    )
            else:
                new_status = "done" if session_type == "rest" else "skipped"

            conn.execute(
                "UPDATE weekly_prescriptions SET status = ?, "
                "actual_activity_id = COALESCE(?, actual_activity_id), "
                "updated_at = now() WHERE prescription_id = ?",
                [new_status, actual_activity_id, row["prescription_id"]],
            )
            counts["updated"] += 1
            counts[new_status] += 1

        logger.info(
            "Reconciled %d prescriptions %s..%s (done=%d replaced=%d skipped=%d)",
            counts["updated"],
            start_date,
            end_date,
            counts["done"],
            counts["replaced"],
            counts["skipped"],
        )

    return counts
