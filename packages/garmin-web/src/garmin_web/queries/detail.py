"""Read-only queries aggregating per-activity detail data."""

import datetime
from typing import Any

import duckdb


def _to_jsonable(value: Any) -> Any:
    """Convert DuckDB date/datetime values to str for JSON serialization."""
    if isinstance(value, datetime.date | datetime.datetime):
        return str(value)
    return value


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    return {col: _to_jsonable(val) for col, val in zip(columns, row, strict=True)}


def _fetch_one(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> dict | None:
    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    row = result.fetchone()
    return _row_to_dict(columns, row) if row is not None else None


def _fetch_all(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    return [_row_to_dict(columns, row) for row in result.fetchall()]


def get_activity_detail(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> dict | None:
    """Aggregate activity detail data into a single dict.

    Combines activities, splits, form_efficiency, heart_rate_zones,
    performance_trends, form_evaluations, vo2_max and lactate_threshold.
    Splits are ordered by split_index ascending; HR zones by zone_number
    ascending.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        Dict with keys: activity, splits, form_efficiency, hr_zones,
        performance_trends, form_evaluations, vo2_max, lactate_threshold.
        Single-row tables that have no row for the activity are None;
        list tables are empty lists.
        Returns None if the activity itself does not exist.
    """
    activity = _fetch_one(
        conn, "SELECT * FROM activities WHERE activity_id = ?", [activity_id]
    )
    if activity is None:
        return None
    return {
        "activity": activity,
        "splits": _fetch_all(
            conn,
            "SELECT * FROM splits WHERE activity_id = ? ORDER BY split_index",
            [activity_id],
        ),
        "form_efficiency": _fetch_one(
            conn,
            "SELECT * FROM form_efficiency WHERE activity_id = ?",
            [activity_id],
        ),
        "hr_zones": _fetch_all(
            conn,
            "SELECT * FROM heart_rate_zones WHERE activity_id = ?"
            " ORDER BY zone_number",
            [activity_id],
        ),
        "performance_trends": _fetch_one(
            conn,
            "SELECT * FROM performance_trends WHERE activity_id = ?",
            [activity_id],
        ),
        "form_evaluations": _fetch_one(
            conn,
            "SELECT * FROM form_evaluations WHERE activity_id = ?",
            [activity_id],
        ),
        "vo2_max": _fetch_one(
            conn,
            "SELECT COALESCE(precise_value, value) AS value, date"
            " FROM vo2_max WHERE activity_id = ?",
            [activity_id],
        ),
        "lactate_threshold": _fetch_one(
            conn,
            "SELECT heart_rate, speed_mps, date_hr"
            " FROM lactate_threshold WHERE activity_id = ?",
            [activity_id],
        ),
    }
