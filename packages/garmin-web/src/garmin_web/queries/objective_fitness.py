"""Read-only objective-fitness trend queries (real-run derived)."""

from itertools import groupby

import duckdb
from garmin_mcp.objective_fitness.critical_speed import quarterly_critical_speed
from garmin_mcp.objective_fitness.segments import run_best_efforts


def get_quarterly_critical_speed(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Quarterly threshold-anchored Critical Speed fit across all runs.

    For each run, the fastest contiguous best-effort segments (2/5/10km
    buckets) are extracted from its 1km splits; their ``(duration, distance)``
    points feed a per-quarter 2-parameter Critical Speed fit
    (``d = CS*t + D'``) over the 2-45 min frontier.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).

    Returns:
        List of dicts sorted by quarter ascending, each with keys
        ``quarter`` (str, ``YYYY-Qn``), ``cs_mps`` (float),
        ``cs_pace_sec_per_km`` (float), ``r_squared`` (float), ``n`` (int) and
        ``label`` (str). ``D'`` is intentionally omitted (invalid here).
    """
    rows = conn.execute("""
        SELECT
            s.activity_id,
            CAST(a.activity_date AS VARCHAR) AS date,
            s.split_index,
            s.distance,
            s.duration_seconds
        FROM splits s
        JOIN activities a USING (activity_id)
        WHERE s.distance IS NOT NULL
          AND s.duration_seconds IS NOT NULL
        ORDER BY s.activity_id, s.split_index
    """).fetchall()

    per_run_efforts: list[tuple[str, float, float]] = []
    for _activity_id, group in groupby(rows, key=lambda r: r[0]):
        run_rows = list(group)
        date = run_rows[0][1]
        splits = [
            {
                "split_index": split_index,
                "distance": distance,
                "duration_seconds": duration_seconds,
            }
            for (_aid, _date, split_index, distance, duration_seconds) in run_rows
        ]
        for effort in run_best_efforts(splits):
            per_run_efforts.append(
                (date, effort.duration_seconds, effort.actual_distance_km * 1000.0)
            )

    result: list[dict] = quarterly_critical_speed(per_run_efforts)
    return result
