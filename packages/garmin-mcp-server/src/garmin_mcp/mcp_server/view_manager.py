"""View Manager for MCP Server

Manages temporary DuckDB views with TTL-based auto-cleanup.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from garmin_mcp.database.connection import get_db_path, get_write_connection

logger = logging.getLogger(__name__)


class ViewManager:
    """Manages temporary DuckDB views with TTL and auto-cleanup."""

    def __init__(self, db_path: str | None = None, max_views: int = 10):
        """Initialize view manager.

        Args:
            db_path: Path to DuckDB database file
            max_views: Maximum number of concurrent views (default 10)
        """
        self.db_path = get_db_path(db_path)
        self.max_views = max_views

        # Track views: {view_name: {"expires_at": timestamp, "created_at": timestamp, "query": str, "row_count": int}}
        self._views: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_view(self, query: str, ttl_seconds: int = 3600) -> dict[str, Any]:
        """Create a temporary view for query reuse.

        Args:
            query: SQL query to materialize as temporary view
            ttl_seconds: Time to live in seconds (default: 1 hour)

        Returns:
            {
                "view": "temp_view_abc123",
                "rows": 1234,
                "expires_at": "2025-10-16T12:00:00Z"
            }
        """
        # Generate unique view name
        unique_id = str(uuid.uuid4())[:8]
        view_name = f"temp_view_{unique_id}"

        # Calculate expiry
        current_time = time.time()
        expires_at = current_time + ttl_seconds

        # Create the view in DuckDB (use regular VIEW, not TEMP, so it persists across connections)
        with get_write_connection(self.db_path) as conn:
            # Create regular view (not TEMP) so it persists across connections
            conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")

            # Get row count
            row_count_result = conn.execute(
                f"SELECT COUNT(*) FROM {view_name}"
            ).fetchone()
            row_count = row_count_result[0] if row_count_result else 0

            # Store metadata
            with self._lock:
                self._views[view_name] = {
                    "expires_at": expires_at,
                    "created_at": current_time,
                    "query": query,
                    "row_count": row_count,
                }

                # Enforce max views limit
                if len(self._views) > self.max_views:
                    self._cleanup_oldest()

        return {
            "view": view_name,
            "rows": row_count,
            "expires_at": datetime.fromtimestamp(expires_at).isoformat() + "Z",
        }

    def view_exists(self, view_name: str) -> bool:
        """Check if view exists and is not expired.

        Args:
            view_name: Name of the view

        Returns:
            True if view exists and not expired
        """
        with self._lock:
            view_info = self._views.get(view_name)

        if view_info is None:
            return False

        # Check if expired
        return not time.time() > view_info["expires_at"]

    def cleanup_view(self, view_name: str) -> None:
        """Remove a specific view.

        Args:
            view_name: Name of the view to remove
        """
        with self._lock:
            if view_name in self._views:
                del self._views[view_name]

        # Drop the view from DuckDB
        try:
            with get_write_connection(self.db_path) as conn:
                conn.execute(f"DROP VIEW IF EXISTS {view_name}")
            logger.debug(f"Removed view: {view_name}")
        except Exception as e:
            logger.warning(f"Failed to drop view {view_name}: {e}")

    def cleanup_expired_views(self) -> None:
        """Remove all expired views."""
        current_time = time.time()

        with self._lock:
            expired_views = [
                view_name
                for view_name, info in self._views.items()
                if current_time > info["expires_at"]
            ]

        for view_name in expired_views:
            self.cleanup_view(view_name)

        if expired_views:
            logger.info(f"Cleaned up {len(expired_views)} expired views")

    def _cleanup_oldest(self) -> None:
        """Remove oldest view when max_views limit is exceeded.

        Called internally when max_views limit is reached.
        """
        if not self._views:
            return

        # Find oldest view by created_at timestamp
        oldest_view = min(self._views.items(), key=lambda item: item[1]["created_at"])
        oldest_view_name = oldest_view[0]

        # Remove oldest view
        del self._views[oldest_view_name]
        logger.info(
            f"Removed oldest view {oldest_view_name} (max_views={self.max_views} exceeded)"
        )

    def get_view_info(self, view_name: str) -> dict[str, Any] | None:
        """Get view information.

        Args:
            view_name: Name of the view

        Returns:
            View info dict or None if expired/not found
        """
        with self._lock:
            view_info = self._views.get(view_name)

        if view_info is None:
            return None

        # Check if expired
        if time.time() > view_info["expires_at"]:
            self.cleanup_view(view_name)
            return None

        return {
            "view": view_name,
            "rows": view_info["row_count"],
            "expires_at": datetime.fromtimestamp(view_info["expires_at"]).isoformat()
            + "Z",
            "query": view_info["query"],
        }

    def cleanup_all(self) -> None:
        """Remove all views (for testing/shutdown)."""
        with self._lock:
            view_names = list(self._views.keys())

        for view_name in view_names:
            self.cleanup_view(view_name)


# Singleton instance
_view_manager: ViewManager | None = None


def get_view_manager() -> ViewManager:
    """Get singleton view manager instance."""
    global _view_manager
    if _view_manager is None:
        _view_manager = ViewManager()
    return _view_manager
