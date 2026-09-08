"""One schema-initialised DuckDB template per test process (#1062).

``GarminDBWriter(db_path)`` builds the full 27-table schema and runs every
migration: ~1-2 s of DDL and a ~3.5 MB file each time. The suite used to do
that in 89 places, writing 687 files / 2.2 GB per run to the overlay ``/tmp``
and stalling random tests for 40-57 s under load.

``init_schema`` runs that DDL once per process (once per xdist worker) into a
process-private template and copies the file for every caller. It is a plain
function, not a fixture, so helper functions that only receive a ``db_path``
can use it too. Tests that must start from an OLD on-disk schema (migration
behaviour) keep calling ``GarminDBWriter`` directly; tests that only verify
the schema use the ``memory_db_path`` fixture instead.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

_TEMPLATE: Path | None = None


def _template() -> Path:
    """Build (once) and return the process-private schema template.

    The writer-built file carries the copy-on-write leftovers of 25 migrations
    (~2.8 MB for an empty schema); ``COPY FROM DATABASE`` into a fresh file
    with 16 KB blocks yields the identical catalog (tables, columns, indexes,
    sequences, constraints, ``schema_version`` — verified) at ~1.3 MB, which
    halves what every test copy writes to ``/tmp``.
    """
    global _TEMPLATE
    if _TEMPLATE is None:
        import duckdb

        from garmin_mcp.database.db_writer import GarminDBWriter

        tmp_dir = Path(tempfile.mkdtemp(prefix="garmin-schema-template-"))
        atexit.register(shutil.rmtree, tmp_dir, ignore_errors=True)
        built = tmp_dir / "built.duckdb"
        GarminDBWriter(db_path=str(built))

        compact = tmp_dir / "template.duckdb"
        duckdb.connect(str(compact), config={"default_block_size": "16384"}).close()
        conn = duckdb.connect(str(built))
        try:
            conn.execute(f"ATTACH '{compact}' AS compact")
            conn.execute("COPY FROM DATABASE built TO compact")
            conn.execute("DETACH compact")
        finally:
            conn.close()
        built.unlink()
        _TEMPLATE = compact
    return _TEMPLATE


def init_schema(db_path: str | Path) -> Path:
    """Create ``db_path`` as a fresh copy of the schema template.

    Equivalent to ``GarminDBWriter(db_path=str(db_path))`` for a path that does
    not exist yet, minus the DDL cost. Overwrites an existing file.
    """
    dest = Path(db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_template(), dest)
    return dest
