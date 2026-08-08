"""Data fetching utilities for form baseline evaluation.

Handles fetching splits data from DuckDB for evaluation.
"""

from typing import Any

from garmin_mcp.database.connection import get_connection
from garmin_mcp.form_baseline.split_filter import (
    running_split_params,
    running_split_sql,
)

_AGGREGATES = """
    AVG(pace_seconds_per_km) as pace_s_per_km,
    AVG(ground_contact_time) as gct_ms,
    AVG(vertical_oscillation) as vo_cm,
    AVG(vertical_ratio) as vr_pct,
    AVG(cadence) as cadence,
    COUNT(*) as split_count
"""

_FORM_METRICS_PRESENT = """
    ground_contact_time IS NOT NULL
    AND vertical_oscillation IS NOT NULL
    AND vertical_ratio IS NOT NULL
"""


def get_splits_data(
    db_path: str,
    activity_id: int,
) -> dict[str, Any]:
    """Get average splits data from DuckDB.

    Uses Work/Run splits only for more accurate evaluation:
    - Interval training: Extracts Work splits (excludes Recovery/Cooldown)
    - Tempo/threshold: Extracts Run phase splits (excludes Warmup/Cooldown)
    - Recovery run: Uses all splits if run_splits covers entire activity

    On top of that phase selection, walk breaks and GPS-fragment laps are
    excluded via :func:`~garmin_mcp.form_baseline.split_filter.running_split_sql`
    so the averages describe the same population the baseline models were
    trained on (#878). ``run_splits`` cannot do this on its own because a
    deliberate walk lap is still recorded with ``role_phase='run'``.

    When that filter would leave no rows at all -- walk-dominated sessions
    slower than 10:00/km exist in the history -- the unfiltered average is
    returned instead so such activities stay evaluable, flagged by
    ``running_splits_only=False``.

    Args:
        db_path: Path to DuckDB database
        activity_id: Activity ID

    Returns:
        Dictionary with average form metrics:
            - pace_s_per_km: Average pace (seconds per km)
            - gct_ms: Average ground contact time (ms)
            - vo_cm: Average vertical oscillation (cm)
            - vr_pct: Average vertical ratio (%)
            - cadence: Average cadence (spm)
            - running_splits_only: True when the running filter was applied,
              False when it matched nothing and the unfiltered average is used
            - split_count: Number of splits behind the returned averages
            - excluded_split_count: Splits dropped by the running filter
              (always 0 when ``running_splits_only`` is False)

    Raises:
        ValueError: If no splits found for activity
    """
    with get_connection(db_path) as conn:
        # Get run_splits from performance_trends
        run_splits_result = conn.execute(
            """
            SELECT run_splits
            FROM performance_trends
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        # Build the phase-selection clause based on run_splits availability
        if run_splits_result and run_splits_result[0]:
            # Parse run_splits: "3,4,6,7,9,10,12,13" -> [3,4,6,7,9,10,12,13]
            split_indices = [int(s.strip()) for s in run_splits_result[0].split(",")]
            phase_clause = f" AND split_index IN ({','.join('?' * len(split_indices))})"
            phase_params: list[Any] = list(split_indices)
        else:
            # Fallback: Use all splits (backward compatibility)
            phase_clause = ""
            phase_params = []

        base_where = f"activity_id = ?{phase_clause} AND {_FORM_METRICS_PRESENT}"
        base_params: list[Any] = [activity_id, *phase_params]

        # Preferred path: running splits only (no walk breaks, no GPS fragments)
        running = conn.execute(
            f"SELECT {_AGGREGATES} FROM splits "
            f"WHERE {base_where} AND {running_split_sql()}",
            [*base_params, *running_split_params()],
        ).fetchone()

        if running is not None and running[0] is not None:
            running_splits_only = True
            result: tuple[Any, ...] = running
            total = conn.execute(
                f"SELECT COUNT(*) FROM splits WHERE {base_where}",
                base_params,
            ).fetchone()
            excluded = int(total[0]) - int(running[5]) if total is not None else 0
        else:
            # Every split is a walk / fragment: keep the activity evaluable.
            running_splits_only = False
            unfiltered = conn.execute(
                f"SELECT {_AGGREGATES} FROM splits WHERE {base_where}",
                base_params,
            ).fetchone()
            if unfiltered is None or unfiltered[0] is None:
                raise ValueError(f"No splits found for activity {activity_id}")
            result = unfiltered
            excluded = 0

        pace_s_per_km, gct_ms, vo_cm, vr_pct, cadence, split_count = result

        return {
            "pace_s_per_km": float(pace_s_per_km),
            "gct_ms": float(gct_ms),
            "vo_cm": float(vo_cm),
            "vr_pct": float(vr_pct),
            "cadence": float(cadence) if cadence is not None else 0.0,
            "running_splits_only": running_splits_only,
            "split_count": int(split_count),
            "excluded_split_count": excluded,
        }
