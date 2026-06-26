"""Strength-training (補強) ingest: discover, aggregate and upsert summaries.

Discovers ``strength_training`` activities in a date window from the Garmin
Connect API, aggregates each session's ACTIVE exercise-set categories into a
``category_counts`` map, and upserts a summary row into the dedicated
``strength_sessions`` table (issue #450).

Discovery uses ``get_activities_by_date(start, end)`` **without** an
``activitytype`` filter and then keeps only entries whose
``activityType.typeKey == 'strength_training'``: ``strength_training`` is a
sub-type and a type-filtered call returns HTTP 400. Runs (``distance > 0``)
are excluded so the run-centric ``activities`` table stays clean.

``category_counts`` is derived from
``/activity-service/activity/{id}/exerciseSets`` by counting ACTIVE sets per
``category`` (e.g. ``{"CRUNCH": 4, "PLANK": 7}``).
"""

from __future__ import annotations

import json
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

_STRENGTH_TYPE_KEY = "strength_training"
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
          ``strength_sessions.activity_date`` in the DB, or ``end - 30 days``
          when the table is empty. (Sessions already stored in the window are
          skipped by the caller, not re-fetched.)
    """
    resolved_end = end_date if end_date is not None else date.today().isoformat()

    if start_date is not None:
        return start_date, resolved_end

    latest = GarminDBReader(db_path=resolved_path).get_latest_strength_date()
    if latest is not None:
        return latest, resolved_end

    end_obj = date.fromisoformat(resolved_end)
    floor = end_obj - timedelta(days=_EMPTY_DB_FLOOR_DAYS)
    return floor.isoformat(), resolved_end


def ingest_strength_sessions(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Discover and upsert strength_training summaries (catch-up aware).

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``). When omitted,
            catch-up resolution is used: the latest stored strength date, or
            ``end - 30`` days when the table is empty. Sessions already stored
            within the window are skipped (not re-fetched).
        end_date: Inclusive window end (``YYYY-MM-DD``). Defaults to today.
        db_path: Optional DuckDB path (defaults to the configured database).

    Returns:
        Dict ``{"discovered", "ingested", "skipped_existing", "activity_ids",
        "window"}`` where ``window`` is ``{"start": str, "end": str}`` (the
        resolved range). ``discovered`` counts strength sessions matched in the
        window; ``ingested`` counts newly fetched + saved sessions;
        ``skipped_existing`` counts sessions already in ``strength_sessions``
        (skipped without an exercise_sets API call). Mirrors
        :func:`ingest_running_activities`.
    """
    resolved_path = str(get_db_path(db_path))
    # Ensure the schema (and strength_sessions table) exists.
    GarminDBWriter(db_path=resolved_path)

    window_start, window_end = _resolve_window(start_date, end_date, resolved_path)

    client = get_garmin_client()
    activities = client.get_activities_by_date(window_start, window_end)
    strength = [a for a in activities if _is_strength(a)]

    ingested = 0
    skipped_existing = 0
    activity_ids: list[int] = []

    for activity in strength:
        activity_id = int(activity["activityId"])

        # exists-first: skip already-stored sessions WITHOUT calling the
        # per-session exercise_sets API (mirrors running_ingest). Strength
        # exercise sets do not change after the fact, so a refresh is moot.
        with get_connection(resolved_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM strength_sessions WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
        if exists is not None:
            skipped_existing += 1
            continue

        exercise_sets = client.get_activity_exercise_sets(activity_id)
        category_counts = _aggregate_categories(exercise_sets)
        row = _build_row(activity, category_counts)

        with get_write_connection(resolved_path) as conn:
            _upsert(conn, row)

        ingested += 1
        activity_ids.append(activity_id)

    return {
        "discovered": len(strength),
        "ingested": ingested,
        "skipped_existing": skipped_existing,
        "activity_ids": activity_ids,
        "window": {"start": window_start, "end": window_end},
    }


def _is_strength(activity: dict[str, Any]) -> bool:
    """Return True for a strength_training entry that is not a distance run."""
    type_key = (activity.get("activityType") or {}).get("typeKey")
    if type_key != _STRENGTH_TYPE_KEY:
        return False
    # Defensive: never let a distance-bearing activity into strength_sessions.
    distance = activity.get("distance")
    return not (distance is not None and float(distance) > 0)


def _aggregate_categories(exercise_sets: dict[str, Any]) -> dict[str, int]:
    """Count ACTIVE exercise sets per ``category``.

    Args:
        exercise_sets: The ``exerciseSets`` payload for an activity.

    Returns:
        Mapping of category name -> number of ACTIVE sets. REST sets and sets
        whose category is missing or ``"UNKNOWN"`` are ignored. Empty dict when
        no ACTIVE sets exist.

    Note:
        Garmin nests the category under ``exercises[].category`` rather than at
        the set level, so the first exercise's category is used per ACTIVE set.
    """
    counts: dict[str, int] = {}
    for entry in exercise_sets.get("exerciseSets") or []:
        if entry.get("setType") != "ACTIVE":
            continue
        exercises = entry.get("exercises") or []
        category = exercises[0].get("category") if exercises else None
        if not category or category == "UNKNOWN":
            continue
        counts[category] = counts.get(category, 0) + 1
    return counts


def _build_row(
    activity: dict[str, Any], category_counts: dict[str, int]
) -> dict[str, Any]:
    """Map a Garmin activity summary + category counts to a table row dict."""
    start_time_local = activity.get("startTimeLocal")
    activity_date = (
        start_time_local.split(" ")[0]
        if isinstance(start_time_local, str) and start_time_local
        else None
    )
    return {
        "activity_id": int(activity["activityId"]),
        "activity_date": activity_date,
        "start_time_local": start_time_local,
        "activity_name": activity.get("activityName"),
        "active_duration_seconds": _to_int(activity.get("movingDuration")),
        "elapsed_duration_seconds": _to_int(activity.get("duration")),
        "avg_heart_rate": _to_int(activity.get("averageHR")),
        "max_heart_rate": _to_int(activity.get("maxHR")),
        "calories": _to_int(activity.get("calories")),
        "active_sets": _to_int(activity.get("activeSets")),
        "total_sets": _to_int(activity.get("totalSets")),
        "category_counts": json.dumps(category_counts, ensure_ascii=False),
        "ingested_at": datetime.now(UTC).replace(tzinfo=None),
    }


_INSERT_COLUMNS = [
    "activity_id",
    "activity_date",
    "start_time_local",
    "activity_name",
    "active_duration_seconds",
    "elapsed_duration_seconds",
    "avg_heart_rate",
    "max_heart_rate",
    "calories",
    "active_sets",
    "total_sets",
    "category_counts",
    "ingested_at",
]


def _upsert(conn: Any, row: dict[str, Any]) -> None:
    """Idempotent upsert keyed on ``activity_id`` (delete + insert)."""
    conn.execute(
        "DELETE FROM strength_sessions WHERE activity_id = ?",
        [row["activity_id"]],
    )
    placeholders = ", ".join(["?"] * len(_INSERT_COLUMNS))
    conn.execute(
        f"""
        INSERT INTO strength_sessions ({", ".join(_INSERT_COLUMNS)})
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
