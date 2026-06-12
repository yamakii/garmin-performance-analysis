"""Read-only queries for the time_series_metrics table with downsampling."""

import duckdb

# Metric columns of time_series_metrics (everything except the key columns
# activity_id / seq_no / timestamp_s). Source of truth:
# garmin_mcp/database/db_writer.py CREATE TABLE time_series_metrics.
ALLOWED_METRICS: frozenset[str] = frozenset(
    {
        "sum_moving_duration",
        "sum_duration",
        "sum_elapsed_duration",
        "sum_distance",
        "sum_accumulated_power",
        "heart_rate",
        "speed",
        "grade_adjusted_speed",
        "cadence",
        "cadence_single_foot",
        "cadence_total",
        "power",
        "ground_contact_time",
        "vertical_oscillation",
        "vertical_ratio",
        "stride_length",
        "vertical_speed",
        "elevation",
        "air_temperature",
        "latitude",
        "longitude",
        "available_stamina",
        "potential_stamina",
        "body_battery",
        "performance_condition",
    }
)


def get_time_series(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    metrics: list[str],
    max_points: int = 500,
) -> dict:
    """Fetch time series metrics, downsampled to at most max_points.

    Rows are ordered by seq_no. When the row count exceeds max_points,
    rows are picked at equal intervals; the first and last rows are
    always kept.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.
        metrics: Metric column names; each must be in ALLOWED_METRICS.
        max_points: Maximum number of points per series (>= 2).

    Returns:
        {"timestamps": [...], "metrics": {name: [...]}}.

    Raises:
        ValueError: If metrics is empty, contains an unknown metric,
            or max_points < 2.
    """
    if not metrics:
        raise ValueError("At least one metric is required")
    unknown = sorted(set(metrics) - ALLOWED_METRICS)
    if unknown:
        raise ValueError(f"Unknown metrics: {', '.join(unknown)}")
    if max_points < 2:
        raise ValueError("max_points must be >= 2")

    # Deduplicate while preserving order
    metric_names = list(dict.fromkeys(metrics))

    # Safe to interpolate: validated against ALLOWED_METRICS above.
    columns = ", ".join(metric_names)
    rows = conn.execute(
        f"SELECT timestamp_s, {columns} FROM time_series_metrics"
        " WHERE activity_id = ? ORDER BY seq_no",
        [activity_id],
    ).fetchall()

    n = len(rows)
    if n > max_points:
        indices = [round(i * (n - 1) / (max_points - 1)) for i in range(max_points)]
        rows = [rows[i] for i in indices]

    return {
        "timestamps": [row[0] for row in rows],
        "metrics": {
            name: [row[i + 1] for row in rows] for i, name in enumerate(metric_names)
        },
    }
