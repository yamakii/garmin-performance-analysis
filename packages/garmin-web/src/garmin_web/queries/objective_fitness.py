"""Read-only objective-fitness trend queries (real-run derived)."""

from itertools import groupby

import duckdb
from garmin_mcp.fitness.vdot import VDOTCalculator
from garmin_mcp.objective_fitness.critical_speed import quarterly_critical_speed
from garmin_mcp.objective_fitness.curve import rolling_max_curve
from garmin_mcp.objective_fitness.segments import run_best_efforts

# Reference distance used to translate a VDOT difference into a pace gap. 5 km is
# the canonical benchmark and lands the Epic #526 spike gap at ~63 s/km.
_GAP_REFERENCE_DISTANCE_KM = 5.0
# Trailing window (days) for the rolling-max objective fitness curve (#561).
_WINDOW_DAYS = 90
# Nominal best-effort distance buckets extracted per run (#558).
_BUCKETS_KM = (2.0, 5.0, 10.0)


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
                # DB stores splits.distance in km; segments.best_contiguous_segment
                # expects meters (compares against target_distance_km * 1000).
                "distance": distance * 1000.0,
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


def get_objective_fitness_trend(conn: duckdb.DuckDBPyConnection) -> dict:
    """Objective (real-run derived) fitness curve overlaid on Garmin VO2max.

    Each run's 1km splits feed #558's best-effort segment extraction; the
    per-run performance VDOTs are smoothed by #561's rolling trailing-window max
    into an objective, non-optimistic fitness curve. That curve is placed
    side-by-side with Garmin's own VO2max series plus the *optimism gap*
    (Garmin-derived VDOT minus the objective VDOT, in VDOT and s/km).

    ``splits.distance`` is stored in **kilometers** in DuckDB, while
    :func:`run_best_efforts` expects each split's ``distance`` in **meters**, so
    distances are multiplied by 1000 before compute (omitting this silently
    yields an empty curve, see #565).

    Args:
        conn: Open DuckDB connection (read-only is sufficient).

    Returns:
        Dict with keys:
        - ``objective_curve``: ``[{"date", "vdot", "source_distance_km"}, ...]``
          ascending by run day (empty when no splits exist).
        - ``garmin_vo2max``: ``[{"date", "value"}, ...]`` ascending by date.
        - ``optimism_gap``: ``{"garmin_vdot", "objective_vdot", "gap_vdot",
          "gap_pace_sec_per_km"}`` or ``None`` when either series is empty.
    """
    try:
        split_rows = conn.execute("""
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
              AND s.duration_seconds > 0
            ORDER BY s.activity_id, s.split_index
        """).fetchall()

        garmin_rows = conn.execute("""
            SELECT CAST(date AS VARCHAR) AS date, value
            FROM vo2_max
            WHERE value IS NOT NULL AND date IS NOT NULL
            ORDER BY date
        """).fetchall()
    except duckdb.Error:
        return {"objective_curve": [], "garmin_vo2max": [], "optimism_gap": None}

    objective_curve = _build_objective_curve(split_rows)
    garmin_vo2max = [
        {"date": date, "value": float(value)} for date, value in garmin_rows
    ]
    optimism_gap = _build_optimism_gap(objective_curve, garmin_vo2max)

    return {
        "objective_curve": objective_curve,
        "garmin_vo2max": garmin_vo2max,
        "optimism_gap": optimism_gap,
    }


def _build_objective_curve(split_rows: list[tuple]) -> list[dict]:
    """Group splits per run, extract best efforts, roll the trailing-window max."""
    per_run_vdot: list[tuple[str, float, float]] = []
    for _activity_id, group in groupby(split_rows, key=lambda r: r[0]):
        run_rows = list(group)
        date = run_rows[0][1]
        splits = [
            {
                "split_index": split_index,
                # DB stores splits.distance in km; run_best_efforts expects meters.
                "distance": distance * 1000.0,
                "duration_seconds": duration_seconds,
            }
            for (_aid, _date, split_index, distance, duration_seconds) in run_rows
        ]
        for effort in run_best_efforts(splits, _BUCKETS_KM):
            per_run_vdot.append((date, effort.vdot, effort.target_distance_km))

    curve = rolling_max_curve(per_run_vdot, window_days=_WINDOW_DAYS)
    return [
        {
            "date": point.date,
            "vdot": round(point.vdot, 2),
            "source_distance_km": point.source_distance_km,
        }
        for point in curve
    ]


def _build_optimism_gap(
    objective_curve: list[dict], garmin_vo2max: list[dict]
) -> dict | None:
    """Compare the latest Garmin-derived VDOT against the latest objective VDOT."""
    if not objective_curve or not garmin_vo2max:
        return None

    garmin_vdot = VDOTCalculator.vdot_from_vo2max(garmin_vo2max[-1]["value"])
    objective_vdot = float(objective_curve[-1]["vdot"])

    ref_km = _GAP_REFERENCE_DISTANCE_KM
    garmin_time = VDOTCalculator.predict_race_time(garmin_vdot, ref_km)
    objective_time = VDOTCalculator.predict_race_time(objective_vdot, ref_km)

    return {
        "garmin_vdot": round(garmin_vdot, 2),
        "objective_vdot": round(objective_vdot, 2),
        "gap_vdot": round(garmin_vdot - objective_vdot, 2),
        "gap_pace_sec_per_km": round((objective_time - garmin_time) / ref_km, 1),
    }
