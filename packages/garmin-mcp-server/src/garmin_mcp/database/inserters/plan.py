"""Training plan ledger DB inserter.

Persists the two plan concepts introduced in issue #977:

- ``training_blocks`` — the mesocycle ledger. Saves are 洗い替え (DELETE +
  INSERT per ``user_id``, ``sequence`` following list order), mirroring
  ``athlete_goals``; every save also appends a JSON snapshot of the whole list
  to ``training_block_versions`` so overwritten plans stay recoverable.
- ``weekly_prescriptions`` — one row per prescribed session per day. Saves are
  append-only per ``batch_id`` (one save = one batch, latest batch per week is
  canonical); only ``status`` and the Garmin / activity ids are mutated later,
  via :func:`update_prescription_status`.

Validation is deliberately strict and raises ``ValueError`` up front: these rows
are written by an LLM-driven skill, so a malformed date range or session type
must fail loudly rather than land silently in the ledger.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: Phases a training block may declare.
ALLOWED_PHASES = frozenset(
    {"base", "build", "peak", "taper", "race", "recovery", "cutback"}
)

#: Session types a weekly prescription may declare.
ALLOWED_SESSION_TYPES = frozenset(
    {
        "long",
        "easy",
        "recovery",
        "threshold",
        "tempo",
        "strides",
        "rest",
        "strength",
        "cross",
    }
)

#: Lifecycle states of a prescription row.
ALLOWED_STATUSES = frozenset(
    {"prescribed", "registered", "done", "replaced", "skipped"}
)


def _default_db_path() -> str:
    """Resolve the default DuckDB path (never hard-coded by callers)."""
    from garmin_mcp.utils.paths import get_database_dir

    return str(get_database_dir() / "garmin_performance.duckdb")


def _parse_date(value: Any, field: str) -> date:
    """Parse ``value`` into a ``date``, raising ValueError with ``field`` context."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"{field} must be a YYYY-MM-DD date, got {value!r}"
            ) from exc
    raise ValueError(f"{field} is required and must be a YYYY-MM-DD date")


def _validate_ladder(ladder: Any, block_title: str) -> list[dict[str, Any]]:
    """Validate the long-run ladder of a block and return it as a list.

    Each step needs ``week_start`` and exactly one of ``target_km`` /
    ``target_minutes`` (a ``None`` value counts as absent), so a ladder row can
    never be an untargeted placeholder.
    """
    if ladder is None:
        return []
    if not isinstance(ladder, list):
        raise ValueError(f"block {block_title!r}: long_run_ladder must be a list")

    for step in ladder:
        if not isinstance(step, dict):
            raise ValueError(f"block {block_title!r}: ladder step must be an object")
        _parse_date(step.get("week_start"), f"block {block_title!r}: week_start")
        has_km = step.get("target_km") is not None
        has_minutes = step.get("target_minutes") is not None
        if has_km == has_minutes:
            raise ValueError(
                f"block {block_title!r}: ladder step {step.get('week_start')!r} "
                "needs exactly one of target_km / target_minutes"
            )
    return ladder


def _json_or_none(value: Any) -> str | None:
    """Serialize a JSON-able column value, keeping ``None`` as SQL NULL."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def insert_training_blocks(
    blocks: list[dict[str, Any]],
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Replace all training blocks for ``user_id`` and snapshot the new list.

    The canonical rows are replaced wholesale (DELETE + INSERT) with
    ``sequence`` following the supplied list order, and the full list is
    appended to ``training_block_versions`` as one JSON snapshot.

    Args:
        blocks: Block dicts with ``phase``, ``title``, ``start_date``,
            ``end_date`` (required) plus optional ``purpose``, ``weight_mode``,
            ``quality_sessions_per_week``, ``quality_types`` (list),
            ``long_run_ladder`` (list of ``{week_start, target_km |
            target_minutes, hr_ceiling, kind, note}``), ``cutback_rule`` (dict)
            and ``notes``.
        user_id: Ledger owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``{"count": <blocks written>, "version_id": <snapshot version>}``.

    Raises:
        ValueError: On an invalid phase, an inverted date range, or a ladder
            step without ``week_start`` / a single target.
    """
    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    validated: list[tuple[dict[str, Any], date, date]] = []
    for block in blocks:
        title = str(block.get("title") or "")
        if not title:
            raise ValueError("every block needs a title")
        phase = block.get("phase")
        if phase not in ALLOWED_PHASES:
            raise ValueError(
                f"block {title!r}: phase must be one of "
                f"{sorted(ALLOWED_PHASES)}, got {phase!r}"
            )
        start = _parse_date(block.get("start_date"), f"block {title!r}: start_date")
        end = _parse_date(block.get("end_date"), f"block {title!r}: end_date")
        if start > end:
            raise ValueError(
                f"block {title!r}: start_date {start} is after end_date {end}"
            )
        _validate_ladder(block.get("long_run_ladder"), title)
        validated.append((block, start, end))

    with get_write_connection(db_path) as conn:
        conn.execute("DELETE FROM training_blocks WHERE user_id = ?", [user_id])
        for index, (block, start, end) in enumerate(validated, start=1):
            conn.execute(
                """
                INSERT INTO training_blocks (
                    block_id, user_id, sequence, phase, title, start_date,
                    end_date, purpose, weight_mode, quality_sessions_per_week,
                    quality_types, long_run_ladder, cutback_rule, notes
                ) VALUES (
                    nextval('seq_training_blocks_id'), ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                [
                    user_id,
                    index,
                    block.get("phase"),
                    block.get("title"),
                    start,
                    end,
                    block.get("purpose"),
                    block.get("weight_mode"),
                    block.get("quality_sessions_per_week"),
                    _json_or_none(block.get("quality_types")),
                    _json_or_none(block.get("long_run_ladder")),
                    _json_or_none(block.get("cutback_rule")),
                    block.get("notes"),
                ],
            )

        version_row = conn.execute(
            "SELECT nextval('seq_training_block_versions_id')"
        ).fetchone()
        version_id = int(version_row[0]) if version_row is not None else 0
        conn.execute(
            """
            INSERT INTO training_block_versions (version_id, user_id, blocks_data)
            VALUES (?, ?, ?)
            """,
            [version_id, user_id, json.dumps(blocks, ensure_ascii=False, default=str)],
        )

        logger.info(
            "Saved %d training blocks user_id=%s (version_id=%d)",
            len(blocks),
            user_id,
            version_id,
        )

    return {"count": len(blocks), "version_id": version_id}


def insert_weekly_prescriptions(
    week_start_date: str,
    prescriptions: list[dict[str, Any]],
    *,
    review_id: int | None = None,
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Insert one batch of prescriptions for a week (append-only).

    All rows share a freshly allocated ``batch_id``; earlier batches for the
    same week stay untouched and are simply superseded (the reader returns the
    highest ``batch_id`` per week).

    Args:
        week_start_date: Week start (``YYYY-MM-DD``); every row's ``date`` must
            fall in ``[week_start_date, week_start_date + 6]``.
        prescriptions: Row dicts with ``date``, ``session_type``, ``title``
            (required) plus optional ``target_minutes``, ``target_km``,
            ``hr_low``, ``hr_high``, ``pace_low_s_per_km``,
            ``pace_high_s_per_km``, ``rationale`` and ``status``.
        review_id: ``weekly_reviews.review_id`` when saved by a weekly review.
        user_id: Ledger owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``{"batch_id": int, "count": int, "prescription_ids": list[int]}``.

    Raises:
        ValueError: On a date outside the week, an unknown ``session_type`` or
            ``status``, or ``hr_low`` above ``hr_high``.
    """
    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    week_start = _parse_date(week_start_date, "week_start_date")
    week_end = week_start + timedelta(days=6)

    validated: list[tuple[dict[str, Any], date]] = []
    for row in prescriptions:
        title = str(row.get("title") or "")
        if not title:
            raise ValueError("every prescription needs a title")
        session_type = row.get("session_type")
        if session_type not in ALLOWED_SESSION_TYPES:
            raise ValueError(
                f"prescription {title!r}: session_type must be one of "
                f"{sorted(ALLOWED_SESSION_TYPES)}, got {session_type!r}"
            )
        row_date = _parse_date(row.get("date"), f"prescription {title!r}: date")
        if not (week_start <= row_date <= week_end):
            raise ValueError(
                f"prescription {title!r}: date {row_date} is outside the week "
                f"{week_start}..{week_end}"
            )
        status = row.get("status") or "prescribed"
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"prescription {title!r}: status must be one of "
                f"{sorted(ALLOWED_STATUSES)}, got {status!r}"
            )
        hr_low = row.get("hr_low")
        hr_high = row.get("hr_high")
        if hr_low is not None and hr_high is not None and hr_low > hr_high:
            raise ValueError(
                f"prescription {title!r}: hr_low {hr_low} is above hr_high {hr_high}"
            )
        validated.append((row, row_date))

    prescription_ids: list[int] = []
    with get_write_connection(db_path) as conn:
        batch_row = conn.execute(
            "SELECT nextval('seq_weekly_prescription_batches')"
        ).fetchone()
        batch_id = int(batch_row[0]) if batch_row is not None else 0

        for row, row_date in validated:
            id_row = conn.execute(
                "SELECT nextval('seq_weekly_prescriptions_id')"
            ).fetchone()
            prescription_id = int(id_row[0]) if id_row is not None else 0
            conn.execute(
                """
                INSERT INTO weekly_prescriptions (
                    prescription_id, batch_id, user_id, review_id,
                    week_start_date, date, session_type, title, target_minutes,
                    target_km, hr_low, hr_high, pace_low_s_per_km,
                    pace_high_s_per_km, rationale, status
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    prescription_id,
                    batch_id,
                    user_id,
                    review_id,
                    week_start,
                    row_date,
                    row.get("session_type"),
                    row.get("title"),
                    row.get("target_minutes"),
                    row.get("target_km"),
                    row.get("hr_low"),
                    row.get("hr_high"),
                    row.get("pace_low_s_per_km"),
                    row.get("pace_high_s_per_km"),
                    row.get("rationale"),
                    row.get("status") or "prescribed",
                ],
            )
            prescription_ids.append(prescription_id)

        logger.info(
            "Saved %d prescriptions user_id=%s week_start_date=%s (batch_id=%d)",
            len(prescription_ids),
            user_id,
            week_start,
            batch_id,
        )

    return {
        "batch_id": batch_id,
        "count": len(prescription_ids),
        "prescription_ids": prescription_ids,
    }


def update_prescription_status(
    prescription_id: int,
    status: str,
    *,
    garmin_workout_id: int | None = None,
    garmin_schedule_id: int | None = None,
    actual_activity_id: int | None = None,
    db_path: str | None = None,
) -> bool:
    """Set a prescription's status (and optional ids), refreshing ``updated_at``.

    Only the ids that are supplied are written; omitted ones keep their stored
    value, so registering a Garmin workout and later linking the actual activity
    are independent updates.

    Args:
        prescription_id: Row identifier from ``insert_weekly_prescriptions``.
        status: One of ``prescribed`` / ``registered`` / ``done`` / ``replaced``
            / ``skipped``.
        garmin_workout_id: Garmin workout id to record (optional).
        garmin_schedule_id: Garmin schedule id to record (optional).
        actual_activity_id: Linked activity id to record (optional).
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``True`` when a row was updated, ``False`` when the id does not exist.

    Raises:
        ValueError: When ``status`` is not a known lifecycle state.
    """
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(ALLOWED_STATUSES)}, got {status!r}"
        )

    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    assignments = ["status = ?", "updated_at = now()"]
    params: list[Any] = [status]
    if garmin_workout_id is not None:
        assignments.append("garmin_workout_id = ?")
        params.append(garmin_workout_id)
    if garmin_schedule_id is not None:
        assignments.append("garmin_schedule_id = ?")
        params.append(garmin_schedule_id)
    if actual_activity_id is not None:
        assignments.append("actual_activity_id = ?")
        params.append(actual_activity_id)
    params.append(prescription_id)

    with get_write_connection(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM weekly_prescriptions WHERE prescription_id = ?",
            [prescription_id],
        ).fetchone()
        if exists is None:
            logger.warning(
                "Prescription %s not found; no status update", prescription_id
            )
            return False

        conn.execute(
            f"UPDATE weekly_prescriptions SET {', '.join(assignments)} "
            "WHERE prescription_id = ?",
            params,
        )

    return True
