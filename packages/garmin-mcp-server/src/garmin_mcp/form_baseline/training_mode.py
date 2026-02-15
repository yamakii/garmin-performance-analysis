"""Training mode detection from hr_efficiency table."""

import duckdb


def get_training_mode(activity_id: int, db_path: str | None = None) -> str:
    """Get training mode from hr_efficiency table.

    Args:
        activity_id: Activity ID to look up
        db_path: Path to DuckDB database. If None, uses GARMIN_DATA_DIR/database/garmin_performance.duckdb

    Returns:
        Training mode: 'interval_sprint', 'tempo_threshold', or 'low_moderate' (default)

    Notes:
        - Returns 'low_moderate' if training_type is NULL or activity not found
        - Maps hr_efficiency.training_type directly to training mode
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    conn = duckdb.connect(db_path, read_only=True)

    try:
        result = conn.execute(
            """
            SELECT training_type
            FROM hr_efficiency
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        if result and result[0]:
            # Return training_type from hr_efficiency
            training_type: str = result[0]
            return training_type
        else:
            # Default to low_moderate if not found or NULL
            return "low_moderate"

    finally:
        conn.close()
