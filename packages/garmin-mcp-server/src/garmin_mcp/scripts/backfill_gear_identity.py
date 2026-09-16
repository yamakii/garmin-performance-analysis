#!/usr/bin/env python3
"""Backfill the gear columns on ``activities`` from the raw gear.json files.

Covers the identity columns added by migration 27 (``gear_nickname`` /
``gear_uuid``) and the lifecycle columns added by migration 28
(``gear_max_km`` / ``gear_status`` / ``gear_since_date`` /
``gear_retired_date``). Both migrations leave existing rows NULL, but the
values were already fetched -- every ingested activity has a ``gear.json``
under ``data/raw/activity/{id}/`` -- so this reads those files and UPDATEs the
columns in place.

Unlike ``regenerate_duckdb --tables activities --force`` this never deletes a
row: it only writes the gear columns, so an activity whose raw file has gone
missing keeps the gear it already has rather than losing it.

Runs offline (no Garmin API calls) and is idempotent -- re-running it rewrites
the same values.

Usage:
    uv run python -m garmin_mcp.scripts.backfill_gear_identity
    uv run python -m garmin_mcp.scripts.backfill_gear_identity --dry-run
    uv run python -m garmin_mcp.scripts.backfill_gear_identity --db-path /path/to.duckdb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from garmin_mcp.database.connection import (
    get_connection,
    get_db_path,
    get_write_connection,
)
from garmin_mcp.database.inserters.activities import _gear_date, _gear_max_km
from garmin_mcp.utils.paths import get_raw_dir


def _read_gear_entry(gear_file: Path) -> dict[str, Any] | None:
    """Return the first gear entry from a raw gear.json, or None.

    Mirrors the list/dict handling in ``inserters/activities.py``. An empty
    list means no gear was registered in Garmin for that activity, which is the
    case for every run before 2021.
    """
    try:
        raw = json.loads(gear_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(raw, list):
        return raw[0] if raw and isinstance(raw[0], dict) else None
    if isinstance(raw, dict):
        return raw
    return None


def backfill_gear_identity(
    db_path: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Populate gear_nickname / gear_uuid from the raw gear.json files.

    Args:
        db_path: Path to DuckDB database. None uses the configured default.
        dry_run: Count what would change without writing.

    Returns:
        Summary dict with the activity counts for each outcome.
    """
    resolved = get_db_path(db_path)
    raw_dir = get_raw_dir() / "activity"

    with get_connection(resolved) as conn:
        activity_ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT activity_id FROM activities ORDER BY activity_date"
            ).fetchall()
        ]

    updates: list[tuple[Any, ...]] = []
    no_raw_file = 0
    no_gear_registered = 0

    for activity_id in activity_ids:
        gear_file = raw_dir / str(activity_id) / "gear.json"
        if not gear_file.exists():
            no_raw_file += 1
            continue
        entry = _read_gear_entry(gear_file)
        if entry is None:
            no_gear_registered += 1
            continue
        updates.append(
            (
                entry.get("displayName"),
                entry.get("uuid"),
                _gear_max_km(entry.get("maximumMeters")),
                entry.get("gearStatusName"),
                _gear_date(entry.get("dateBegin")),
                _gear_date(entry.get("dateEnd")),
                activity_id,
            )
        )

    if not dry_run and updates:
        with get_write_connection(str(resolved)) as conn:
            conn.executemany(
                """
                UPDATE activities
                SET gear_nickname = ?,
                    gear_uuid = ?,
                    gear_max_km = ?,
                    gear_status = ?,
                    gear_since_date = ?,
                    gear_retired_date = ?
                WHERE activity_id = ?
                """,
                updates,
            )

    return {
        "activities_scanned": len(activity_ids),
        "activities_updated": len(updates),
        "no_raw_file": no_raw_file,
        "no_gear_registered": no_gear_registered,
        "dry_run": dry_run,
    }


def main() -> int:
    """CLI entry point. Emits a single-line JSON summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Backfill gear_nickname / gear_uuid from raw gear.json files."
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to DuckDB database (default: $GARMIN_DATA_DIR/database/...)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute counts without writing to the database.",
    )
    args = parser.parse_args()

    result = backfill_gear_identity(db_path=args.db_path, dry_run=args.dry_run)
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
