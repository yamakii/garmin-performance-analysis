"""Export Manager for MCP Server

Manages temporary file exports with TTL-based auto-cleanup.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


class ExportManager:
    """Manages temporary exports with TTL and auto-cleanup."""

    def __init__(self, export_dir: Path | str = "/tmp/garmin_exports"):
        """Initialize export manager.

        Args:
            export_dir: Directory for temporary exports
        """
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        # Track exports: {handle: expiry_timestamp}
        self._exports: dict[str, float] = {}
        self._lock = threading.Lock()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def create_export_handle(
        self, export_format: Literal["parquet", "csv"], ttl_seconds: int = 3600
    ) -> tuple[Path, str, float]:
        """Create a new export file handle.

        Args:
            export_format: Export format (parquet or csv)
            ttl_seconds: Time to live in seconds (default: 1 hour)

        Returns:
            Tuple of (file_path, handle_str, expires_at_timestamp)
        """
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"export_{timestamp}_{unique_id}.{export_format}"
        file_path = self.export_dir / filename

        # Calculate expiry
        expires_at = time.time() + ttl_seconds

        # Register export
        handle = str(file_path)
        with self._lock:
            self._exports[handle] = expires_at

        return file_path, handle, expires_at

    def get_export_info(self, handle: str) -> dict | None:
        """Get export information.

        Args:
            handle: Export file path

        Returns:
            Export info dict or None if expired/not found
        """
        with self._lock:
            expires_at = self._exports.get(handle)

        if expires_at is None:
            return None

        if time.time() > expires_at:
            self._remove_export(handle)
            return None

        file_path = Path(handle)
        if not file_path.exists():
            self._remove_export(handle)
            return None

        return {
            "handle": handle,
            "expires_at": datetime.fromtimestamp(expires_at).isoformat() + "Z",
            "size_mb": file_path.stat().st_size / (1024 * 1024),
        }

    def _remove_export(self, handle: str) -> None:
        """Remove export file and tracking entry.

        Args:
            handle: Export file path
        """
        with self._lock:
            self._exports.pop(handle, None)

        try:
            Path(handle).unlink(missing_ok=True)
            logger.debug(f"Removed expired export: {handle}")
        except Exception as e:
            logger.warning(f"Failed to remove export {handle}: {e}")

    def _cleanup_loop(self) -> None:
        """Background cleanup loop (runs every 5 minutes)."""
        while True:
            time.sleep(300)  # 5 minutes
            self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        """Remove all expired exports."""
        current_time = time.time()

        with self._lock:
            expired_handles = [
                handle
                for handle, expires_at in self._exports.items()
                if current_time > expires_at
            ]

        for handle in expired_handles:
            self._remove_export(handle)

        if expired_handles:
            logger.info(f"Cleaned up {len(expired_handles)} expired exports")

    def cleanup_all(self) -> None:
        """Remove all exports (for testing/shutdown)."""
        with self._lock:
            handles = list(self._exports.keys())

        for handle in handles:
            self._remove_export(handle)


# Singleton instance
_export_manager: ExportManager | None = None


def get_export_manager() -> ExportManager:
    """Get singleton export manager instance."""
    global _export_manager
    if _export_manager is None:
        _export_manager = ExportManager()
    return _export_manager
