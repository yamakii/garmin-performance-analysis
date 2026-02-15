"""
Base DuckDB reader with connection management.

Provides common utilities for all reader classes.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

import duckdb

from garmin_mcp.database.connection import get_connection, get_db_path

logger = logging.getLogger(__name__)


class BaseDBReader:
    """Base class for DuckDB readers with connection management."""

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB reader with database path.

        Args:
            db_path: Optional path to DuckDB database file.
                    If None, uses default path from config.
        """
        self.db_path = get_db_path(db_path)
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
        with get_connection(self.db_path) as conn:
            yield conn
