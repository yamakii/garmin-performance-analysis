"""Hiking (山行) ingest: discover and upsert summary rows.

Discovers ``hiking`` activities in a date window from the Garmin Connect API and
upserts a summary row into the dedicated ``hiking_sessions`` table (issue #921).
Hiking is kept out of ``activities`` on purpose: a hike carries distance and a
large elevation profile but its pace/HR relationship is nothing like a run, so
letting it in would distort every run-centric aggregation (ACWR, load trend,
form baselines). This mirrors the ``strength_sessions`` design (issue #450).

Discovery uses ``get_activities_by_date(start, end)`` **without** an
``activitytype`` filter and then keeps only entries whose
``activityType.typeKey`` is in ``{'hiking', 'mountaineering'}`` — Garmin
records alpine outings as ``mountaineering`` (issue #925) — (a type-filtered
call returns HTTP 400 for sub-types).

Unlike strength, no per-activity detail call is made: every persisted field
(distance, movingDuration, elevationGain/Loss, averageHR, ...) is already
present in the activity-list summary, so a raw cache is unnecessary.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garmin_mcp.database.connection import (
    get_connection,
    get_db_path,
    get_write_connection,
)
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.api_client import get_garmin_client

logger = logging.getLogger(__name__)

_HIKING_TYPE_KEYS = {"hiking", "mountaineering"}
_EMPTY_DB_FLOOR_DAYS = 30


def _resolve_window(
    start_date: str | None,
    end_date: str | None,
    resolved_path: str,
) -> tuple[str, str]:
    """Resolve the inclusive ``(start, end)`` ingest window (catch-up aware).

    Args:
        start_date: Explicit window start (``YYYY-MM-DD``), or ``None`` for
            catch-up resolution.
        end_date: Explicit window end (``YYYY-MM-DD``), or ``None`` for today.
        resolved_path: Path to the DuckDB database (already resolved).

    Returns:
        ``(start, end)`` as ``YYYY-MM-DD`` strings.

        - ``end`` defaults to today when omitted.
        - When ``start`` is given, it is returned unchanged (explicit range).
        - When ``start`` is omitted, catch-up applies: the latest
          ``hiking_sessions.activity_date`` in the DB, or ``end - 30 days``
          when the table is empty. (Sessions already stored in the window are
          skipped by the caller, not re-written.)
    """
    resolved_end = end_date if end_date is not None else date.today().isoformat()

    if start_date is not None:
        return start_date, resolved_end

    latest = GarminDBReader(db_path=resolved_path).get_latest_hiking_date()
    if latest is not None:
        return latest, resolved_end

    end_obj = date.fromisoformat(resolved_end)
    floor = end_obj - timedelta(days=_EMPTY_DB_FLOOR_DAYS)
    return floor.isoformat(), resolved_end


def ingest_hiking_sessions(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Discover and upsert hiking summaries (catch-up aware).

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``). When omitted,
            catch-up resolution is used: the latest stored hiking date, or
            ``end - 30`` days when the table is empty. Sessions already stored
            within the window are skipped.
        end_date: Inclusive window end (``YYYY-MM-DD``). Defaults to today.
        db_path: Optional DuckDB path (defaults to the configured database).

    Returns:
        Dict ``{"discovered", "ingested", "skipped_existing", "activity_ids",
        "window"}`` where ``window`` is ``{"start": str, "end": str}`` (the
        resolved range). ``discovered`` counts hikes matched in the window;
        ``ingested`` counts newly saved sessions; ``skipped_existing`` counts
        sessions already in ``hiking_sessions``. Mirrors
        :func:`ingest_strength_sessions`.
    """
    resolved_path = str(get_db_path(db_path))
    # Ensure the schema (and hiking_sessions table) exists.
    GarminDBWriter(db_path=resolved_path)

    window_start, window_end = _resolve_window(start_date, end_date, resolved_path)

    client = get_garmin_client()
    activities = client.get_activities_by_date(window_start, window_end)
    hikes = [a for a in activities if _is_hiking(a)]

    ingested = 0
    skipped_existing = 0
    activity_ids: list[int] = []

    for activity in hikes:
        activity_id = int(activity["activityId"])

        # exists-first: an already-stored hike is left untouched (its summary
        # does not change after the fact), mirroring running/strength ingest.
        with get_connection(resolved_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM hiking_sessions WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
        if exists is not None:
            skipped_existing += 1
            continue

        row = _build_row(activity)

        with get_write_connection(resolved_path) as conn:
            _upsert(conn, row)

        ingested += 1
        activity_ids.append(activity_id)

    return {
        "discovered": len(hikes),
        "ingested": ingested,
        "skipped_existing": skipped_existing,
        "activity_ids": activity_ids,
        "window": {"start": window_start, "end": window_end},
    }


def _is_hiking(activity: dict[str, Any]) -> bool:
    """Return True for a ``hiking``/``mountaineering`` activity-list entry.

    No distance guard (unlike strength): a hike legitimately carries distance;
    the type key alone decides.
    """
    type_key = (activity.get("activityType") or {}).get("typeKey")
    return type_key in _HIKING_TYPE_KEYS


def _build_row(activity: dict[str, Any]) -> dict[str, Any]:
    """Map a Garmin activity summary to a ``hiking_sessions`` row dict."""
    start_time_local = activity.get("startTimeLocal")
    activity_date = (
        start_time_local.split(" ")[0]
        if isinstance(start_time_local, str) and start_time_local
        else None
    )
    distance_m = _to_float(activity.get("distance"))
    return {
        "activity_id": int(activity["activityId"]),
        "activity_date": activity_date,
        "start_time_local": start_time_local,
        "activity_name": activity.get("activityName"),
        "duration_seconds": _to_int(activity.get("movingDuration")),
        "elapsed_duration_seconds": _to_int(activity.get("duration")),
        "distance_km": None if distance_m is None else distance_m / 1000.0,
        "elevation_gain_m": _to_float(activity.get("elevationGain")),
        "elevation_loss_m": _to_float(activity.get("elevationLoss")),
        "avg_heart_rate": _to_int(activity.get("averageHR")),
        "max_heart_rate": _to_int(activity.get("maxHR")),
        "calories": _to_int(activity.get("calories")),
        "ingested_at": datetime.now(UTC).replace(tzinfo=None),
    }


_INSERT_COLUMNS = [
    "activity_id",
    "activity_date",
    "start_time_local",
    "activity_name",
    "duration_seconds",
    "elapsed_duration_seconds",
    "distance_km",
    "elevation_gain_m",
    "elevation_loss_m",
    "avg_heart_rate",
    "max_heart_rate",
    "calories",
    "ingested_at",
]


def _upsert(conn: Any, row: dict[str, Any]) -> None:
    """Idempotent upsert keyed on ``activity_id`` (delete + insert)."""
    conn.execute(
        "DELETE FROM hiking_sessions WHERE activity_id = ?",
        [row["activity_id"]],
    )
    placeholders = ", ".join(["?"] * len(_INSERT_COLUMNS))
    conn.execute(
        f"""
        INSERT INTO hiking_sessions ({", ".join(_INSERT_COLUMNS)})
        VALUES ({placeholders})
        """,
        [row[col] for col in _INSERT_COLUMNS],
    )


def _to_int(value: Any) -> int | None:
    """Coerce a numeric value to int (or None)."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    """Coerce a numeric value to float (or None).

    Keeps a missing ``elevationLoss`` (absent on some summaries) from failing
    the insert.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
