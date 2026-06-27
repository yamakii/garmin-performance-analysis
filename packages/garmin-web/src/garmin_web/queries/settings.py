"""Read-only access to athlete-level configuration (Issue #605).

Currently exposes the configurable week start day used to align calendar-week
aggregations (e.g. the volume trend) with ``weekly_reviews.week_start_date``.
The value lives in ``athlete_profile.week_start_day`` (Sub-1 / #602). The helper
degrades gracefully when the column, table, or row is absent so the Web app keeps
working before the schema migration lands (defaulting to Monday).
"""

import duckdb

# 0 = Monday .. 6 = Sunday (matches Python's ``date.weekday()``).
_DEFAULT_WEEK_START_DAY = 0


def get_week_start_day(
    conn: duckdb.DuckDBPyConnection, user_id: str = "default"
) -> int:
    """Return the athlete's configured week start day (0=Mon .. 6=Sun).

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        The stored ``week_start_day`` as an int. Falls back to ``0`` (Monday)
        when the ``athlete_profile`` table/column is missing, no row matches the
        ``user_id``, or the stored value is ``NULL``.
    """
    try:
        row = conn.execute(
            "SELECT week_start_day FROM athlete_profile WHERE user_id = ?",
            [user_id],
        ).fetchone()
    except duckdb.Error:
        return _DEFAULT_WEEK_START_DAY
    if row is None or row[0] is None:
        return _DEFAULT_WEEK_START_DAY
    return int(row[0])
