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
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Thread-local storage for read-only connections
_thread_local = threading.local()


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


@contextmanager
def get_connection(
    db_path: str | Path | None = None,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Get a read-only DuckDB connection.

    Creates a new connection per call and closes it when done.
    This is the standard pattern for DuckDB which handles its own
    internal connection pooling.

    Args:
        db_path: Path to database file. If None, uses config default.

    Yields:
        Read-only DuckDB connection.
    """
    path = _resolve_db_path(db_path)
    conn = duckdb.connect(str(path), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_write_connection(
    db_path: str | Path | None = None,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Get a read-write DuckDB connection.

    Creates a new connection per call. DuckDB supports only one
    writer at a time, so write connections should be short-lived.

    Args:
        db_path: Path to database file. If None, uses config default.

    Yields:
        Read-write DuckDB connection.
    """
    path = _resolve_db_path(db_path)
    conn = duckdb.connect(str(path))
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
