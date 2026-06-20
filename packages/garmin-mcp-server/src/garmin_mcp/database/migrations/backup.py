"""Auto-backup a real production DuckDB before pending migrations apply.

Guards against destructive migration changes by copying the live database
to a timestamped backup file before the migration runner mutates it. Only
real production databases (located directly under ``get_database_dir()``)
with pending migrations are backed up; in-memory / temp / fresh /
up-to-date databases are skipped to avoid noise in tests and init churn.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.migrations.registry import MIGRATIONS
from garmin_mcp.utils.paths import get_database_dir

logger = logging.getLogger(__name__)

_KEEP_GENERATIONS = 2


def _read_current_version(db_path: str | Path) -> int:
    """Read max(version) from schema_version via a read-only connection.

    A missing schema_version table (fresh DB) yields a CatalogException,
    which we treat as version 0. This deliberately avoids any write or
    table-creation side effect on the database.
    """
    try:
        with get_connection(db_path) as conn:
            result = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
            assert result is not None
            return int(result[0])
    except duckdb.CatalogException:
        return 0


def backup_if_pending(db_path: str | Path) -> Path | None:
    """Back up a real production DuckDB before pending migrations apply.

    Returns the backup Path, or None if skipped (memory / temp / fresh /
    already up-to-date). Raises RuntimeError if the backup copy fails.
    """
    # 1. In-memory DB has nothing to back up.
    if str(db_path) == ":memory:":
        return None

    path = Path(db_path)

    # 2. Only back up an existing, non-empty file.
    if not path.is_file() or path.stat().st_size == 0:
        return None

    # 3. Only back up the real production DB (directly under the data dir).
    #    This excludes pytest tmp paths and explicit temp paths.
    parent = path.resolve().parent
    if parent != get_database_dir().resolve():
        return None

    # 4. Only back up when there are pending migrations on an existing DB.
    current = _read_current_version(path)
    max_version = max(v for v, _, _ in MIGRATIONS)
    if not (0 < current < max_version):
        return None

    # 5. Create the backup copy (failure is fatal -> RuntimeError).
    stem = path.stem
    dst = parent / f"{stem}_backup_{datetime.now():%Y%m%d_%H%M%S}.duckdb"
    try:
        shutil.copy2(path, dst)
    except Exception as e:  # noqa: BLE001 - re-raised as RuntimeError below
        raise RuntimeError(f"Migration backup failed for {db_path}: {e}") from e

    logger.info("Created migration backup: %s", dst)

    # 6. Prune older generations, keeping the newest two (timestamp-sortable
    #    names). Prune failures are logged and swallowed (non-fatal).
    backups = sorted(parent.glob(f"{stem}_backup_*.duckdb"))
    for stale in backups[:-_KEEP_GENERATIONS]:
        try:
            stale.unlink()
        except OSError as e:
            logger.warning("Failed to prune old backup %s: %s", stale, e)

    # 7. Return the backup path.
    return dst
