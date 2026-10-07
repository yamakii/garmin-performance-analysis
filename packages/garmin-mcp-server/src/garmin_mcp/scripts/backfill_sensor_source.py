#!/usr/bin/env python3
"""Backfill the sensor source columns on ``activities`` from raw activity.json.

Covers ``dynamics_source`` (``pod`` / ``wrist``) and ``hr_source``
(``chest_strap`` / ``wrist``) added by migration 35. The migration leaves
existing rows NULL, but every ingested activity already has an
``activity.json`` under ``data/raw/activity/{id}/`` whose
``metadataDTO.sensors`` list answers it, so this reads those files and UPDATEs
the two columns in place.

Like ``backfill_gear_identity`` this never deletes a row, runs offline (no
Garmin API calls) and is idempotent.

Usage:
    uv run python -m garmin_mcp.scripts.backfill_sensor_source
    uv run python -m garmin_mcp.scripts.backfill_sensor_source --dry-run
    uv run python -m garmin_mcp.scripts.backfill_sensor_source --db-path /path/to.duckdb
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from garmin_mcp.database.connection import (
    get_connection,
    get_db_path,
    get_write_connection,
)
from garmin_mcp.database.inserters.activities import classify_sensors
from garmin_mcp.utils.paths import get_raw_dir


def backfill_sensor_source(
    db_path: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Populate dynamics_source / hr_source from the raw activity.json files.

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

    updates: list[tuple[str, str, int]] = []
    no_raw_file = 0

    for activity_id in activity_ids:
        activity_file = raw_dir / str(activity_id) / "activity.json"
        try:
            raw = json.loads(activity_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            no_raw_file += 1
            continue
        metadata_dto = raw.get("metadataDTO") or {}
        dynamics_source, hr_source = classify_sensors(metadata_dto.get("sensors"))
        updates.append((dynamics_source, hr_source, activity_id))

    if not dry_run and updates:
        with get_write_connection(str(resolved)) as conn:
            conn.executemany(
                """
                UPDATE activities
                SET dynamics_source = ?,
                    hr_source = ?
                WHERE activity_id = ?
                """,
                updates,
            )

    return {
        "activities_scanned": len(activity_ids),
        "activities_updated": len(updates),
        "no_raw_file": no_raw_file,
        "pod_runs": sum(1 for u in updates if u[0] == "pod"),
        "chest_strap_runs": sum(1 for u in updates if u[1] == "chest_strap"),
        "dry_run": dry_run,
    }


def main() -> int:
    """CLI entry point. Emits a single-line JSON summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Backfill dynamics_source / hr_source from raw activity.json."
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

    result = backfill_sensor_source(db_path=args.db_path, dry_run=args.dry_run)
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
