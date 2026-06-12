"""Read-only queries for the activities table."""

import duckdb

_SELECT_ACTIVITIES = """
    SELECT
        activity_id,
        activity_date,
        activity_name,
        total_distance_km,
        total_time_seconds,
        avg_pace_seconds_per_km,
        avg_heart_rate
    FROM activities
"""


def list_activities(
    conn: duckdb.DuckDBPyConnection,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """List activities sorted by activity_date descending.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        from_date: Inclusive lower bound (YYYY-MM-DD), or None.
        to_date: Inclusive upper bound (YYYY-MM-DD), or None.

    Returns:
        List of dicts with keys: activity_id, activity_date (str),
        activity_name, total_distance_km, total_time_seconds,
        avg_pace_seconds_per_km, avg_heart_rate.
    """
    sql = _SELECT_ACTIVITIES
    conditions: list[str] = []
    params: list[str] = []
    if from_date is not None:
        conditions.append("activity_date >= ?")
        params.append(from_date)
    if to_date is not None:
        conditions.append("activity_date <= ?")
        params.append(to_date)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY activity_date DESC"

    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    rows = result.fetchall()

    activities = []
    for row in rows:
        record = dict(zip(columns, row, strict=True))
        # DuckDB returns datetime.date; convert for JSON serialization
        record["activity_date"] = str(record["activity_date"])
        activities.append(record)
    return activities
