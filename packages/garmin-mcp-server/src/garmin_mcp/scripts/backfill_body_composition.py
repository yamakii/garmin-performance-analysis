#!/usr/bin/env python3
"""Backfill the ``body_composition`` table from cached weight JSON.

Scans every ``data/raw/weight/{date}.json`` file and upserts each day into the
``body_composition`` table. The table is keyed by date (unique index), so the
operation is fully idempotent: re-running never duplicates a date.

Empty marker files (``{}``) and files without a ``dateWeightList`` entry are
skipped.

Usage:
    uv run python -m garmin_mcp.scripts.backfill_body_composition
    uv run python -m garmin_mcp.scripts.backfill_body_composition --dry-run
    uv run python -m garmin_mcp.scripts.backfill_body_composition --db-path /path/to.duckdb
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_writer import GarminDBWriter, _body_comp_row
from garmin_mcp.utils.paths import get_weight_raw_dir


def backfill_body_composition(
    db_path: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Backfill the body_composition table from cached weight JSON files.

    Args:
        db_path: Path to DuckDB database (None resolves via ``$GARMIN_DATA_DIR``).
        dry_run: When True, no DB writes occur; counts are still computed
            (``inserted`` = how many rows would be upserted).

    Returns:
        Dict with keys:
            - ``scanned``: weight JSON files scanned
            - ``inserted``: files that yielded a row (upserted, or would be)
            - ``skipped``: files with no usable weight data (empty / no list)
            - ``min_date`` / ``max_date``: date range of inserted rows (or None)
    """
    resolved_db_path = str(get_db_path(db_path))
    weight_raw_dir = get_weight_raw_dir()

    scanned = 0
    inserted = 0
    skipped = 0
    dates: list[str] = []

    # Build the writer once and reuse it (per-file construction is slow).
    writer = None if dry_run else GarminDBWriter(db_path=resolved_db_path)

    weight_files = (
        sorted(weight_raw_dir.glob("*.json")) if weight_raw_dir.exists() else []
    )

    for weight_file in weight_files:
        scanned += 1
        date = weight_file.stem

        try:
            with open(weight_file, encoding="utf-8") as f:
                weight_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            skipped += 1
            print(f"Skipping {weight_file.name}: {e}", file=sys.stderr)
            continue

        if not isinstance(weight_data, dict):
            skipped += 1
            continue

        row = _body_comp_row(date, weight_data)
        if row is None:
            skipped += 1
            continue

        inserted += 1
        dates.append(date)

        if not dry_run:
            assert writer is not None
            writer.insert_body_composition(date, weight_data)

    return {
        "scanned": scanned,
        "inserted": inserted,
        "skipped": skipped,
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }


def main() -> int:
    """CLI entry point. Emits a single-line JSON summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Backfill body_composition table from cached weight JSON."
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

    result = backfill_body_composition(db_path=args.db_path, dry_run=args.dry_run)
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
