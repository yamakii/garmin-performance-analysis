"""Running differential ingest: discover, filter and by-id ingest runs.

Discovers every activity in a date window via
``get_activities_by_date(start, end)`` **without** an ``activitytype`` filter,
keeps only running entries (``typeKey in {"running", "treadmill_running"}`` with
``distance > 0``), drops those already present in the ``activities`` table, and
ingests the remaining activity ids one by one through
``GarminIngestWorker.process_activity`` (by-id, so multiple runs on the same day
are handled — unlike ``process_activity_by_date`` which raises on same-day
duplicates).

Garmin calls are throttled by sleeping ``throttle_seconds`` between activities.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from garmin_mcp.database.connection import get_connection, get_db_path
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.api_client import get_garmin_client
from garmin_mcp.ingest.garmin_worker import GarminIngestWorker

logger = logging.getLogger(__name__)

_RUNNING_TYPE_KEYS = frozenset({"running", "treadmill_running"})


def ingest_running_activities(
    start_date: str,
    end_date: str,
    db_path: str | None = None,
    throttle_seconds: float = 2.0,
) -> dict[str, Any]:
    """Discover and by-id ingest未取り込みのランニング activity in ``[start, end]``.

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``).
        end_date: Inclusive window end (``YYYY-MM-DD``).
        db_path: Optional DuckDB path (defaults to the configured database).
        throttle_seconds: Seconds to sleep between Garmin ingests (rate limit).

    Returns:
        Dict ``{"discovered": int, "ingested": int, "skipped_existing": int,
        "activity_ids": list[int]}``. ``discovered`` counts runs matched by the
        typeKey whitelist; ``ingested`` counts runs newly fetched + saved;
        ``skipped_existing`` counts runs already present in ``activities``;
        ``activity_ids`` lists the newly ingested ids in discovery order.
    """
    resolved_path = str(get_db_path(db_path))
    # Ensure the schema (and activities table) exists before querying it.
    GarminDBWriter(db_path=resolved_path)

    client = get_garmin_client()
    activities = client.get_activities_by_date(start_date, end_date)
    runs = [a for a in activities if _is_running(a)]

    ingested = 0
    skipped_existing = 0
    activity_ids: list[int] = []

    for activity in runs:
        activity_id = int(activity["activityId"])
        if _exists(resolved_path, activity_id):
            skipped_existing += 1
            continue

        date = _activity_date(activity)
        if ingested > 0 and throttle_seconds > 0:
            time.sleep(throttle_seconds)
        worker = GarminIngestWorker(db_path=resolved_path)
        worker.process_activity(activity_id, date)

        ingested += 1
        activity_ids.append(activity_id)

    return {
        "discovered": len(runs),
        "ingested": ingested,
        "skipped_existing": skipped_existing,
        "activity_ids": activity_ids,
    }


def _is_running(activity: dict[str, Any]) -> bool:
    """Return True for a running entry (whitelisted typeKey, distance > 0)."""
    type_key = (activity.get("activityType") or {}).get("typeKey")
    if type_key not in _RUNNING_TYPE_KEYS:
        return False
    distance = activity.get("distance")
    return distance is not None and float(distance) > 0


def _activity_date(activity: dict[str, Any]) -> str:
    """Extract the ``YYYY-MM-DD`` date from a Garmin activity summary."""
    start_time_local = activity.get("startTimeLocal")
    if isinstance(start_time_local, str) and start_time_local:
        return start_time_local.split(" ")[0]
    raise ValueError(
        f"activity {activity.get('activityId')} has no usable startTimeLocal"
    )


def _exists(db_path: str, activity_id: int) -> bool:
    """Return True when ``activity_id`` is already in the ``activities`` table."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM activities WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
    return row is not None
