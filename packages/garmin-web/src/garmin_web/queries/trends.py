"""Read-only trend queries aggregating across activities."""

import datetime as _dt
import json

import duckdb
from garmin_mcp.database.connection import db_path_from_connection
from garmin_mcp.rag.queries.heat_adjustment import REF_TEMP_C, HeatAdjustmentModel

_VALID_GRANULARITIES = ("week", "month")

# Longitudinal trend narration columns (issue #789/#791). analysis_data is a
# JSON string decoded back into a dict; date/timestamp values are stringified.
_NARRATION_COLUMNS = (
    "analysis_id, user_id, granularity, period_start, period_end, "
    "analysis_data, created_at, agent_name, agent_version"
)

# Latest version of the most recent period for a granularity. Multiple versions
# may exist per period (append-only); newest period + newest version wins.
_SELECT_NARRATION_LATEST = f"""
    SELECT {_NARRATION_COLUMNS}
    FROM trend_analyses
    WHERE user_id = ? AND granularity = ?
    ORDER BY period_start DESC, created_at DESC
    LIMIT 1
"""

# All saved versions of a single period, newest first.
_SELECT_NARRATION_VERSIONS = f"""
    SELECT {_NARRATION_COLUMNS}
    FROM trend_analyses
    WHERE user_id = ? AND granularity = ? AND period_start = ?
    ORDER BY created_at DESC
"""


def _narration_row_to_dict(columns: list[str], row: tuple) -> dict:
    """Zip a row into a dict, JSON-decoding analysis_data and stringifying dates."""
    record: dict = {}
    for col, value in zip(columns, row, strict=True):
        if isinstance(value, _dt.date | _dt.datetime):
            record[col] = str(value)
        else:
            record[col] = value
    raw = record.get("analysis_data")
    record["analysis_data"] = json.loads(raw) if raw is not None else None
    return record


def get_trend_narration(
    conn: duckdb.DuckDBPyConnection,
    granularity: str = "week",
    user_id: str = "default",
) -> dict | None:
    """Get the latest-version narration for the most recent period.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        granularity: Trend granularity (``"week"`` | ``"month"``).
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        A narration dict with ``analysis_data`` JSON-decoded and date/timestamp
        values converted to ``str`` (the newest period, its latest version), or
        ``None`` when no narration exists (drives a 404 at the API boundary).
    """
    result = conn.execute(_SELECT_NARRATION_LATEST, [user_id, granularity])
    row = result.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in result.description]
    return _narration_row_to_dict(columns, row)


def list_trend_narration_versions(
    conn: duckdb.DuckDBPyConnection,
    granularity: str,
    period_start: str,
    user_id: str = "default",
) -> list[dict]:
    """List all saved narration versions for a single period, newest first.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        granularity: Trend granularity (``"week"`` | ``"month"``).
        period_start: Period start (``YYYY-MM-DD``), the saved record key.
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        A list of narration dicts ordered by ``created_at`` descending (newest
        first). Each ``analysis_data`` is JSON-decoded and date/timestamp values
        are converted to ``str``. Empty when no versions exist for the period.
    """
    result = conn.execute(
        _SELECT_NARRATION_VERSIONS, [user_id, granularity, period_start]
    )
    columns = [desc[0] for desc in result.description]
    return [_narration_row_to_dict(columns, row) for row in result.fetchall()]


# Calendar month bucket, e.g. "2025-10".
_MONTH_BUCKET = "strftime(activity_date, '%Y-%m')"

# Configurable calendar-week bucket: the date the activity's week starts on,
# e.g. "2025-10-06" (same representation as weekly_reviews.week_start_date).
# isodow() is 1=Mon .. 7=Sun; the ``?`` parameter is week_start_day (0=Mon ..
# 6=Sun, matching Python's date.weekday()). The modulo shifts each date back to
# its week-start date; the offset is cast to INTEGER because DATE - <int> days
# requires an INTEGER (a BIGINT modulo result has no DATE subtraction overload).
_WEEK_BUCKET = (
    "CAST(activity_date - "
    "CAST((isodow(activity_date) - 1 - ? + 7) % 7 AS INTEGER) AS VARCHAR)"
)


def _rows_to_dicts(result: duckdb.DuckDBPyConnection) -> list[dict]:
    """Convert a DuckDB result to a list of dicts keyed by column name."""
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def get_volume_trend(
    conn: duckdb.DuckDBPyConnection,
    granularity: str = "week",
    week_start_day: int = 0,
) -> list[dict]:
    """Aggregate running volume per calendar week or calendar month.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        granularity: "week" (calendar week keyed by its start date, e.g.
            "2025-10-06") or "month" (e.g. "2025-10").
        week_start_day: Day the week starts on (0=Mon .. 6=Sun, matching
            Python's ``date.weekday()``). Only affects "week" granularity.

    Returns:
        List of dicts sorted by bucket ascending, each with keys:
        bucket (str), distance_km (float), duration_seconds (int),
        run_count (int). For "week" the bucket is the week's start date as
        "YYYY-MM-DD"; for "month" it is "YYYY-MM".

    Raises:
        ValueError: If granularity is not "week" or "month".
    """
    if granularity not in _VALID_GRANULARITIES:
        raise ValueError(
            f"granularity must be one of {_VALID_GRANULARITIES}, got {granularity!r}"
        )
    if granularity == "week":
        bucket_expr = _WEEK_BUCKET
        params: list = [week_start_day]
    else:
        bucket_expr = _MONTH_BUCKET
        params = []
    result = conn.execute(
        f"""
        SELECT
            {bucket_expr} AS bucket,
            COALESCE(SUM(total_distance_km), 0.0) AS distance_km,
            CAST(COALESCE(SUM(total_time_seconds), 0) AS INTEGER)
                AS duration_seconds,
            COUNT(*) AS run_count
        FROM activities
        GROUP BY bucket
        ORDER BY bucket
    """,
        params,
    )
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


def get_heat_adjusted_trend(
    conn: duckdb.DuckDBPyConnection,
    start_date: str,
    end_date: str,
    ref_temp_c: float = REF_TEMP_C,
) -> dict:
    """Climate-neutral HR-at-pace trend with per-run heat_cost.

    Extracts the running activity IDs within ``[start_date, end_date]`` from
    the ``activities`` table, then delegates the regression fit and the
    per-run climate-neutral HR derivation to the single-source
    :class:`~garmin_mcp.rag.queries.heat_adjustment.HeatAdjustmentModel`
    (Issue #549). The model re-reads HR / pace / temperature for those
    activities via ``GarminDBReader`` against the same database file (resolved
    from ``conn`` so the web layer never hard-codes a path).

    Args:
        conn: Open read-only DuckDB connection to the garmin database.
        start_date: Inclusive lower date bound (YYYY-MM-DD).
        end_date: Inclusive upper date bound (YYYY-MM-DD).
        ref_temp_c: Hinge breakpoint in °C below which no heat penalty applies.

    Returns:
        The dict produced by ``HeatAdjustmentModel.compute_trend`` — the same
        shape (status / coefficients / neutral_hr_slope / points) used by the
        MCP tool. When fewer than the model's minimum number of complete rows
        fall in range, ``{"status": "insufficient_data", ...}`` is returned.
    """
    rows = conn.execute(
        """
        SELECT activity_id
        FROM activities
        WHERE activity_date BETWEEN ? AND ?
        ORDER BY activity_date
        """,
        [start_date, end_date],
    ).fetchall()
    activity_ids = [int(row[0]) for row in rows]

    # Resolve the database file backing this connection so the model's reader
    # opens the same file (a second read-only connection is safe). An empty
    # path (e.g. an in-memory connection) falls back to the config default.
    db_path = db_path_from_connection(conn)

    model = HeatAdjustmentModel(db_path=db_path, ref_temp_c=ref_temp_c)
    result: dict = model.compute_trend(activity_ids, start_date, end_date)
    return result


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
