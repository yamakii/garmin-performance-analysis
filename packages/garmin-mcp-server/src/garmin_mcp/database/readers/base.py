"""
Base DuckDB reader with connection management.

Provides common utilities for all reader classes.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class BaseDBReader:
    """Base class for DuckDB readers with connection management."""

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB reader with database path.

        Args:
            db_path: Optional path to DuckDB database file.
                    If None, uses default path from garmin_mcp.utils.paths.
        """
        if db_path is None:
            from garmin_mcp.utils.paths import get_database_dir

            db_path = str(get_database_dir() / "garmin_performance.duckdb")

        self.db_path = Path(db_path)
        if not self.db_path.exists():
            logger.warning(f"Database not found: {self.db_path}")

    @contextmanager
    def _get_connection(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Get read-only DuckDB connection as context manager.

        Yields:
            Read-only DuckDB connection

        Example:
            >>> with self._get_connection() as conn:
            ...     result = conn.execute("SELECT * FROM activities").fetchone()
        """
        conn = duckdb.connect(str(self.db_path), read_only=True)
        try:
            yield conn
        finally:
            conn.close()
