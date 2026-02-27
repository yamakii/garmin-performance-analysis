"""Data fetching utilities for form baseline evaluation.

Handles fetching splits data from DuckDB for evaluation.
"""

from garmin_mcp.database.connection import get_connection


def get_splits_data(
    db_path: str,
    activity_id: int,
) -> dict[str, float]:
    """Get average splits data from DuckDB.

    Uses Work/Run splits only for more accurate evaluation:
    - Interval training: Extracts Work splits (excludes Recovery/Cooldown)
    - Tempo/threshold: Extracts Run phase splits (excludes Warmup/Cooldown)
    - Recovery run: Uses all splits if run_splits covers entire activity

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

        # Build WHERE clause based on run_splits availability
        if run_splits_result and run_splits_result[0]:
            # Parse run_splits: "3,4,6,7,9,10,12,13" -> [3,4,6,7,9,10,12,13]
            run_splits = run_splits_result[0]
            split_indices = [int(s.strip()) for s in run_splits.split(",")]

            # Use only Work/Run splits for evaluation
            result = conn.execute(
                f"""
                SELECT
                    AVG(pace_seconds_per_km) as pace_s_per_km,
                    AVG(ground_contact_time) as gct_ms,
                    AVG(vertical_oscillation) as vo_cm,
                    AVG(vertical_ratio) as vr_pct,
                    AVG(cadence) as cadence
                FROM splits
                WHERE activity_id = ?
                  AND split_index IN ({','.join('?' * len(split_indices))})
                  AND ground_contact_time IS NOT NULL
                  AND vertical_oscillation IS NOT NULL
                  AND vertical_ratio IS NOT NULL
            """,
                [activity_id] + split_indices,
            ).fetchone()
        else:
            # Fallback: Use all splits (backward compatibility)
            result = conn.execute(
                """
                SELECT
                    AVG(pace_seconds_per_km) as pace_s_per_km,
                    AVG(ground_contact_time) as gct_ms,
                    AVG(vertical_oscillation) as vo_cm,
                    AVG(vertical_ratio) as vr_pct,
                    AVG(cadence) as cadence
                FROM splits
                WHERE activity_id = ?
                  AND ground_contact_time IS NOT NULL
                  AND vertical_oscillation IS NOT NULL
                  AND vertical_ratio IS NOT NULL
            """,
                [activity_id],
            ).fetchone()

        if not result or result[0] is None:
            raise ValueError(f"No splits found for activity {activity_id}")

        pace_s_per_km, gct_ms, vo_cm, vr_pct, cadence = result

        return {
            "pace_s_per_km": float(pace_s_per_km),
            "gct_ms": float(gct_ms),
            "vo_cm": float(vo_cm),
            "vr_pct": float(vr_pct),
            "cadence": float(cadence) if cadence is not None else 0.0,
        }
