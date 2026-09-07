"""Read-only queries for the weekly_reviews table.

Reads per-week review records saved by the CLI (`/weekly-review`). The Web app
is display-only; registration/updates are owned by the CLI. Each ``review_data``
payload is JSON-decoded back into a dict and all date/timestamp values are
converted to ``str`` so the result is JSON-serializable at the MCP/API boundary.

``review_data.verdict`` is **derived**, not stored: the per-day plan (session,
rating, comment) lives in ``weekly_prescriptions`` only, so the verdict is
projected from the batch linked to the review version — else the week's
canonical batch, else the stored payload for pre-split reviews (Issue #1021).
``garmin_web`` never imports ``garmin_mcp``, so this mirrors the derivation in
``garmin_mcp.database.readers.athlete`` rather than sharing it.
"""

import datetime as _dt
import json

import duckdb

_REVIEW_COLUMNS = (
    "review_id, user_id, week_start_date, week_end_date, review_date, "
    "review_data, created_at, agent_name, agent_version"
)

# One row per week: keep the latest version (highest created_at) per
# week_start_date so the list view shows a single canonical review per week.
_SELECT_LIST = f"""
    SELECT {_REVIEW_COLUMNS}
    FROM weekly_reviews
    WHERE user_id = ?
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY week_start_date ORDER BY created_at DESC
    ) = 1
    ORDER BY week_start_date DESC
    LIMIT ?
"""

# Latest version for a given week (multiple versions may exist after #312).
_SELECT_ONE = f"""
    SELECT {_REVIEW_COLUMNS}
    FROM weekly_reviews
    WHERE user_id = ? AND week_start_date = ?
    ORDER BY created_at DESC
    LIMIT 1
"""

# All saved versions for a given week, newest first.
_SELECT_VERSIONS = f"""
    SELECT {_REVIEW_COLUMNS}
    FROM weekly_reviews
    WHERE user_id = ? AND week_start_date = ?
    ORDER BY created_at DESC
"""


_PRESCRIPTION_COLUMNS = (
    "prescription_id, batch_id, date, session_type, title, target_minutes, "
    "target_km, hr_low, hr_high, rationale, rating, status"
)

# Highest batch matching the predicate; the params are (user_id, value) twice.
_SELECT_PRESCRIPTIONS = """
    SELECT {columns}
    FROM weekly_prescriptions
    WHERE user_id = ? AND {where}
      AND batch_id = (
          SELECT MAX(batch_id) FROM weekly_prescriptions
          WHERE user_id = ? AND {where}
      )
    ORDER BY date, prescription_id
"""


def _review_row_to_dict(columns: list[str], row: tuple) -> dict:
    """Zip a row into a dict, JSON-decoding review_data and stringifying dates."""
    record: dict = {}
    for col, value in zip(columns, row, strict=True):
        if isinstance(value, _dt.date | _dt.datetime):
            record[col] = str(value)
        else:
            record[col] = value
    raw = record.get("review_data")
    record["review_data"] = json.loads(raw) if raw is not None else None
    return record


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    """Zip a plain row into a dict, converting date/datetime values to str."""
    return {
        col: (str(value) if isinstance(value, _dt.date | _dt.datetime) else value)
        for col, value in zip(columns, row, strict=True)
    }


def _prescription_rows(
    conn: duckdb.DuckDBPyConnection, where: str, params: list
) -> list[dict]:
    """Fetch the highest-batch prescription rows matching ``where``.

    Returns an empty list when nothing matches or the table/column is missing
    (databases older than the ``rating`` migration).
    """
    sql = _SELECT_PRESCRIPTIONS.format(columns=_PRESCRIPTION_COLUMNS, where=where)
    try:
        result = conn.execute(sql, params)
        rows = result.fetchall()
    except duckdb.Error:
        return []
    columns = [desc[0] for desc in result.description]
    return [_row_to_dict(columns, row) for row in rows]


def _verdict_from_prescriptions(rows: list[dict]) -> list[dict]:
    """Project prescription rows into the review's per-day verdict rows."""
    return [
        {
            "date": row.get("date"),
            "session": row.get("title"),
            "rating": row.get("rating"),
            "comment": row.get("rationale"),
            "session_type": row.get("session_type"),
            "target_km": row.get("target_km"),
            "target_minutes": row.get("target_minutes"),
            "hr_low": row.get("hr_low"),
            "hr_high": row.get("hr_high"),
            "status": row.get("status"),
            "prescription_id": row.get("prescription_id"),
        }
        for row in rows
    ]


def _attach_verdict(conn: duckdb.DuckDBPyConnection, record: dict) -> dict:
    """Derive ``review_data.verdict`` from the week's prescriptions.

    Three steps: the batch linked to this review version, else the week's
    canonical batch (a prose-only revision appends a version without a new
    batch), else the stored payload. Sets ``verdict_source``
    (``"prescriptions"`` / ``"stored"``) and ``prescription_batch_id``.
    ``record`` is mutated in place and returned; a ``None`` ``review_data``
    is left untouched.
    """
    review_data = record.get("review_data")
    if not isinstance(review_data, dict):
        return record

    user_id = record.get("user_id") or "default"
    rows: list[dict] = []
    review_id = record.get("review_id")
    if review_id is not None:
        rows = _prescription_rows(
            conn, "review_id = ?", [user_id, review_id, user_id, review_id]
        )
    week_start_date = record.get("week_start_date")
    if not rows and week_start_date is not None:
        rows = _prescription_rows(
            conn,
            "week_start_date = CAST(? AS DATE)",
            [user_id, week_start_date, user_id, week_start_date],
        )

    if rows:
        review_data["verdict"] = _verdict_from_prescriptions(rows)
        review_data["verdict_source"] = "prescriptions"
        review_data["prescription_batch_id"] = rows[0].get("batch_id")
    else:
        review_data["verdict_source"] = "stored"
        review_data["prescription_batch_id"] = None
    return record


def list_weekly_reviews(
    conn: duckdb.DuckDBPyConnection,
    limit: int = 12,
    user_id: str = "default",
) -> list[dict]:
    """List recent weekly reviews in descending week order.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        limit: Maximum number of reviews to return (default 12).
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        A list of review dicts (newest first). Each ``review_data`` is
        JSON-decoded back into a dict; date/timestamp values are ``str``.
    """
    result = conn.execute(_SELECT_LIST, [user_id, limit])
    columns = [desc[0] for desc in result.description]
    return [
        _attach_verdict(conn, _review_row_to_dict(columns, row))
        for row in result.fetchall()
    ]


def get_weekly_review(
    conn: duckdb.DuckDBPyConnection,
    week_start_date: str,
    user_id: str = "default",
) -> dict | None:
    """Get a single weekly review by its week-start date.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        week_start_date: Week start (``YYYY-MM-DD``), the saved record key.
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        A review dict with ``review_data`` JSON-decoded and date/timestamp
        values converted to ``str``, or ``None`` when no matching review exists.
    """
    result = conn.execute(_SELECT_ONE, [user_id, week_start_date])
    row = result.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in result.description]
    return _attach_verdict(conn, _review_row_to_dict(columns, row))


def list_weekly_review_versions(
    conn: duckdb.DuckDBPyConnection,
    week_start_date: str,
    user_id: str = "default",
) -> list[dict]:
    """List all saved versions for a single week, newest first.

    Multiple versions per week may exist since #312 (each `/weekly-review`
    run appends a new row instead of overwriting). The detail page uses this
    to let the user switch between past versions of the same week.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        week_start_date: Week start (``YYYY-MM-DD``), the saved record key.
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        A list of review dicts ordered by ``created_at`` descending (newest
        first). Each ``review_data`` is JSON-decoded back into a dict and
        date/timestamp values are converted to ``str``. Empty when no
        versions exist for the week.
    """
    result = conn.execute(_SELECT_VERSIONS, [user_id, week_start_date])
    columns = [desc[0] for desc in result.description]
    return [
        _attach_verdict(conn, _review_row_to_dict(columns, row))
        for row in result.fetchall()
    ]
