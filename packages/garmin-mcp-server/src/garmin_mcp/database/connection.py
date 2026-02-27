"""Centralized DuckDB connection management.

Provides thread-safe connection factory for DuckDB, replacing scattered
duckdb.connect() calls throughout the codebase.

Usage:
    from garmin_mcp.database.connection import get_connection, get_write_connection

    # Read-only (most common)
    with get_connection(db_path) as conn:
        result = conn.execute("SELECT * FROM activities").fetchall()

    # Write access
    with get_write_connection(db_path) as conn:
        conn.execute("INSERT INTO ...")
"""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def _resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve database path from argument or config.

    Uses get_database_dir() directly (not cached get_config()) to ensure
    environment variable changes are respected at call time.

    Args:
        db_path: Explicit path, or None to use default.

    Returns:
        Resolved Path to database file.
    """
    if db_path is not None:
        return Path(db_path)

    from garmin_mcp.utils.paths import get_database_dir

    return get_database_dir() / "garmin_performance.duckdb"


def _connect_with_retry(
    path: Path,
    *,
    read_only: bool = False,
    retries: int = 3,
    backoff: float = 2.0,
) -> duckdb.DuckDBPyConnection:
    """Connect to DuckDB with retry on lock errors.

    DuckDB supports only one writer at a time. When concurrent access
    causes lock contention, this retries with linear backoff.

    Args:
        path: Path to database file.
        read_only: Whether to open in read-only mode.
        retries: Maximum number of retry attempts.
        backoff: Base delay in seconds (linear: backoff, 2*backoff, ...).

    Returns:
        DuckDB connection.

    Raises:
        duckdb.IOException: If lock cannot be acquired after all retries,
            or if the error is not lock-related.
    """
    for attempt in range(retries + 1):
        try:
            return duckdb.connect(str(path), read_only=read_only)
        except duckdb.IOException as e:
            if "Could not set lock" not in str(e):
                raise
            if attempt == retries:
                raise
            delay = backoff * (attempt + 1)
            logger.warning(
                "DuckDB lock contention on %s, retrying in %.1fs " "(attempt %d/%d)",
                path,
                delay,
                attempt + 1,
                retries,
            )
            time.sleep(delay)
    # Unreachable, but satisfies type checker
    raise RuntimeError("Unreachable")  # pragma: no cover


@contextmanager
def get_connection(
    db_path: str | Path | None = None,
    *,
    retries: int = 3,
    backoff: float = 2.0,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Get a read-only DuckDB connection.

    Creates a new connection per call and closes it when done.
    This is the standard pattern for DuckDB which handles its own
    internal connection pooling.

    Args:
        db_path: Path to database file. If None, uses config default.
        retries: Maximum retry attempts on lock errors.
        backoff: Base delay in seconds for linear backoff.

    Yields:
        Read-only DuckDB connection.
    """
    path = _resolve_db_path(db_path)
    conn = _connect_with_retry(path, read_only=True, retries=retries, backoff=backoff)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_write_connection(
    db_path: str | Path | None = None,
    *,
    retries: int = 3,
    backoff: float = 2.0,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Get a read-write DuckDB connection.

    Creates a new connection per call. DuckDB supports only one
    writer at a time, so write connections should be short-lived.

    Args:
        db_path: Path to database file. If None, uses config default.
        retries: Maximum retry attempts on lock errors.
        backoff: Base delay in seconds for linear backoff.

    Yields:
        Read-write DuckDB connection.
    """
    path = _resolve_db_path(db_path)
    conn = _connect_with_retry(path, read_only=False, retries=retries, backoff=backoff)
    try:
        yield conn
    finally:
        conn.close()


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Get resolved database path.

    Convenience function for code that needs the path but not a connection.

    Args:
        db_path: Explicit path, or None to use config default.

    Returns:
        Resolved Path to database file.
    """
    return _resolve_db_path(db_path)
