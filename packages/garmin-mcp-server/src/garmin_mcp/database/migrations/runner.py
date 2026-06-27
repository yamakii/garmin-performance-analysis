"""Lightweight migration runner with schema_version tracking.

Tracks which migrations have been applied to the DuckDB database and runs
pending migrations in order. The schema_version table is the source of truth.
"""

import logging
from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_db_path, get_write_connection

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Run and track database migrations."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = get_db_path(db_path)

    def _ensure_schema_version_table(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create schema_version table if it doesn't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

    def get_current_version(self) -> int:
        """Read max(version) from schema_version table. Returns 0 if empty."""
        with get_write_connection(self.db_path) as conn:
            self._ensure_schema_version_table(conn)
            result = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
            assert result is not None
            return int(result[0])

    def run_pending(self) -> list[str]:
        """Run all migrations above current_version. Returns applied names."""
        from .registry import MIGRATIONS

        with get_write_connection(self.db_path) as conn:
            self._ensure_schema_version_table(conn)

            result = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
            assert result is not None
            current = int(result[0])

            applied: list[str] = []
            for version, name, migrate_fn in MIGRATIONS:
                if version <= current:
                    continue
                logger.info("Applying migration %d: %s", version, name)
                migrate_fn(conn)
                conn.execute(
                    "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                    [version, name],
                )
                applied.append(name)
                logger.info("Applied migration %d: %s", version, name)

            return applied


def ensure_schema_current(db_path: str | Path | None = None) -> list[str]:
    """Apply pending migrations (idempotent). Returns applied names.

    Thin startup helper that backs up a real production DB (when it has pending
    migrations) and then runs every migration above the on-disk
    ``schema_version``. Safe to call at server/worker bootstrap before any tool
    is served: when the schema already matches the registry maximum this is a
    no-op (returns ``[]``) and re-running it never raises.

    This decouples schema migration from ``GarminDBWriter`` construction so that
    read-only paths (e.g. ``get_athlete_profile``) also see an up-to-date schema
    instead of crashing on a column a newer reader expects (issue #631).

    Args:
        db_path: Explicit database path, or ``None`` to resolve the default.

    Returns:
        The names of the migrations applied during this call (empty when the
        schema was already current).
    """
    from garmin_mcp.database.migrations.backup import backup_if_pending

    resolved = get_db_path(db_path)
    # Best-effort safety net: copy the real production DB before mutating it.
    # No-op for temp/in-memory/fresh/up-to-date databases.
    backup_if_pending(resolved)
    return MigrationRunner(resolved).run_pending()
