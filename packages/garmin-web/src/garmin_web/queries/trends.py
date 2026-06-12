"""Read-only trend queries aggregating across activities."""

import duckdb

_VALID_GRANULARITIES = ("week", "month")

_BUCKET_EXPRESSIONS = {
    # ISO week, e.g. "2025-W41" (isoyear/weekofyear are ISO-8601 in DuckDB)
    "week": "printf('%d-W%02d', isoyear(activity_date), weekofyear(activity_date))",
    # Calendar month, e.g. "2025-10"
    "month": "strftime(activity_date, '%Y-%m')",
}


def _rows_to_dicts(result: duckdb.DuckDBPyConnection) -> list[dict]:
    """Convert a DuckDB result to a list of dicts keyed by column name."""
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def get_volume_trend(
    conn: duckdb.DuckDBPyConnection, granularity: str = "week"
) -> list[dict]:
    """Aggregate running volume per ISO week or calendar month.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        granularity: "week" (ISO week, e.g. "2025-W41") or
            "month" (e.g. "2025-10").

    Returns:
        List of dicts sorted by bucket ascending, each with keys:
        bucket (str), distance_km (float), duration_seconds (int),
        run_count (int).

    Raises:
        ValueError: If granularity is not "week" or "month".
    """
    if granularity not in _VALID_GRANULARITIES:
        raise ValueError(
            f"granularity must be one of {_VALID_GRANULARITIES}, got {granularity!r}"
        )
    bucket_expr = _BUCKET_EXPRESSIONS[granularity]
    result = conn.execute(f"""
        SELECT
            {bucket_expr} AS bucket,
            COALESCE(SUM(total_distance_km), 0.0) AS distance_km,
            CAST(COALESCE(SUM(total_time_seconds), 0) AS INTEGER)
                AS duration_seconds,
            COUNT(*) AS run_count
        FROM activities
        GROUP BY bucket
        ORDER BY bucket
    """)
    return _rows_to_dicts(result)


def get_physiology_trend(conn: duckdb.DuckDBPyConnection) -> dict:
    """Time series of VO2max and lactate threshold measurements.

    Returns:
        Dict with keys:
        - "vo2max": list of {"date": str, "value": float}, date ascending.
        - "lactate_threshold": list of
          {"date": str, "heart_rate": int, "speed_mps": float},
          date ascending.
    """
    # NOTE: conn.execute() returns the connection itself, so each result
    # must be fully consumed before the next query is executed.
    vo2max = _rows_to_dicts(conn.execute("""
            SELECT
                CAST(date AS VARCHAR) AS date,
                COALESCE(precise_value, value) AS value
            FROM vo2_max
            WHERE date IS NOT NULL
            ORDER BY date
        """))
    lactate = _rows_to_dicts(conn.execute("""
            SELECT
                CAST(CAST(date_hr AS DATE) AS VARCHAR) AS date,
                heart_rate,
                speed_mps
            FROM lactate_threshold
            WHERE date_hr IS NOT NULL
            ORDER BY date_hr
        """))
    return {"vo2max": vo2max, "lactate_threshold": lactate}


def get_form_trend(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Form evaluation scores joined with activity dates.

    Returns:
        List of dicts sorted by date ascending, each with keys:
        date (str), overall_score (float), gct_delta (float, %),
        vo_delta (float, cm), vr_delta (float, %).
    """
    result = conn.execute("""
        SELECT
            CAST(a.activity_date AS VARCHAR) AS date,
            f.overall_score,
            f.gct_delta_pct AS gct_delta,
            f.vo_delta_cm AS vo_delta,
            f.vr_delta_pct AS vr_delta
        FROM form_evaluations f
        JOIN activities a USING (activity_id)
        ORDER BY a.activity_date
    """)
    return _rows_to_dicts(result)


def get_efficiency_trend(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """HR efficiency metrics joined with activity dates.

    Returns:
        List of dicts sorted by date ascending, each with keys:
        date (str), aerobic_efficiency (str rating), primary_zone (str),
        zone1_percentage .. zone5_percentage (float).
    """
    result = conn.execute("""
        SELECT
            CAST(a.activity_date AS VARCHAR) AS date,
            h.aerobic_efficiency,
            h.primary_zone,
            h.zone1_percentage,
            h.zone2_percentage,
            h.zone3_percentage,
            h.zone4_percentage,
            h.zone5_percentage
        FROM hr_efficiency h
        JOIN activities a USING (activity_id)
        ORDER BY a.activity_date
    """)
    return _rows_to_dicts(result)
