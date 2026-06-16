"""Read-only queries for the weekly_reviews table.

Reads per-week review records saved by the CLI (`/weekly-review`). The Web app
is display-only; registration/updates are owned by the CLI. Each ``review_data``
payload is JSON-decoded back into a dict and all date/timestamp values are
converted to ``str`` so the result is JSON-serializable at the MCP/API boundary.
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
    return [_review_row_to_dict(columns, row) for row in result.fetchall()]


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
    return _review_row_to_dict(columns, row)


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
    return [_review_row_to_dict(columns, row) for row in result.fetchall()]
