"""Utility functions for form baseline system."""

import pandas as pd


def drop_outliers(
    df: pd.DataFrame, column: str, valid_range: tuple[float, float]
) -> pd.DataFrame:
    """
    Remove outliers from DataFrame based on valid range.

    Args:
        df: Input DataFrame
        column: Column name to check for outliers
        valid_range: Tuple of (min, max) valid values

    Returns:
        DataFrame with outliers removed

    Examples:
        >>> df = pd.DataFrame({'gct_ms': [50, 200, 250, 500]})
        >>> result = drop_outliers(df, 'gct_ms', (100, 400))
        >>> len(result)
        2
    """
    min_val, max_val = valid_range
    mask = (df[column] >= min_val) & (df[column] <= max_val)
    return df[mask].copy()


def resolve_dynamics_source(conn, activity_id: int) -> str:
    """Return the dynamics sensor of an activity, ``'all'`` when it is unknown.

    The form expectation models are trained and applied per
    ``activities.dynamics_source`` (#1631). Only a NULL / missing sensor (e.g. a
    run ingested without ``activity.json``) maps to ``'all'``, the legacy
    mixed-sensor model; a known sensor never falls back to it.

    Args:
        conn: DuckDB connection
        activity_id: Garmin activity ID

    Returns:
        The sensor name (``'pod'``, ``'wrist'``, ...) or ``'all'``.
    """
    row = conn.execute(
        "SELECT dynamics_source FROM activities WHERE activity_id = ?",
        [activity_id],
    ).fetchone()
    if row is None or not row[0]:
        return "all"
    return str(row[0])


def to_speed(pace_seconds_per_km: float) -> float:
    """
    Convert pace (sec/km) to speed (m/s).

    Args:
        pace_seconds_per_km: Pace in seconds per kilometer

    Returns:
        Speed in meters per second

    Raises:
        ValueError: If pace is zero or negative

    Examples:
        >>> to_speed(300.0)  # 5:00/km
        3.333...
        >>> to_speed(240.0)  # 4:00/km
        4.166...
    """
    if pace_seconds_per_km <= 0:
        raise ValueError("Pace must be positive")

    return 1000.0 / pace_seconds_per_km
