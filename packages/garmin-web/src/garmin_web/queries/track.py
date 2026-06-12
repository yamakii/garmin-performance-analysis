"""Read-only query for GPS track points from time_series_metrics."""

import duckdb


def get_track(conn: duckdb.DuckDBPyConnection, activity_id: int) -> list[dict]:
    """Fetch the GPS coordinate sequence ordered by seq_no.

    Rows where latitude or longitude is NULL (e.g. indoor runs or GPS
    dropouts) are excluded.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        List of {"seq_no": int, "lat": float, "lon": float}, ordered by
        seq_no ascending. Empty list when the activity has no GPS data.
    """
    rows = conn.execute(
        "SELECT seq_no, latitude, longitude FROM time_series_metrics"
        " WHERE activity_id = ?"
        " AND latitude IS NOT NULL AND longitude IS NOT NULL"
        " ORDER BY seq_no",
        [activity_id],
    ).fetchall()
    return [{"seq_no": row[0], "lat": row[1], "lon": row[2]} for row in rows]
