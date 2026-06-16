#!/usr/bin/env python3
"""Backfill ``activities.base_weight_kg`` for rows where it is NULL.

For each activity whose ``base_weight_kg`` is NULL, recompute the 7-day median
weight (cache-first, see :func:`GarminIngestWorker._calculate_median_weight`)
and UPDATE the row. Activities whose median cannot be resolved (no cached body
composition data within the 7-day window) are skipped.

Activities that get a freshly populated ``base_weight_kg`` are then re-evaluated
via :func:`evaluate_and_store`, which recomputes ``power_*`` / ``integrated_score``
in ``form_evaluations`` (the power calculation reads ``base_weight_kg`` from the
``activities`` table).

Network safety:
    To avoid hammering the Garmin Connect API, body composition lookups are
    forced **cache-only**. The worker's ``collect_body_composition_data`` is
    wrapped so that only previously saved raw JSON files (under
    ``data/raw/weight/{date}.json``) are read; missing days return ``None``
    instead of triggering an API fetch.

Usage:
    uv run python -m garmin_mcp.scripts.backfill_base_weight
    uv run python -m garmin_mcp.scripts.backfill_base_weight --dry-run
    uv run python -m garmin_mcp.scripts.backfill_base_weight --db-path /path/to.duckdb
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
from garmin_mcp.form_baseline.evaluator import evaluate_and_store
from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


def _load_cached_body_composition(
    weight_raw_dir: Path, date: str
) -> dict[str, Any] | None:
    """Read body composition data from cache only (never hits the API).

    Mirrors the cache-read branch of
    :func:`garmin_mcp.ingest.raw_data_fetcher.collect_body_composition_data`,
    but returns ``None`` (instead of fetching) when no cache file exists.

    Args:
        weight_raw_dir: Directory holding ``{date}.json`` weight cache files.
        date: Date in YYYY-MM-DD format.

    Returns:
        Cached raw weight data dict, or ``None`` if missing / empty marker.
    """
    weight_file = weight_raw_dir / f"{date}.json"
    if not weight_file.exists():
        return None
    with open(weight_file, encoding="utf-8") as f:
        cached_data = json.load(f)
    # Empty dict is a "no data" marker file.
    if not cached_data:
        return None
    return cached_data  # type: ignore[no-any-return]


def _make_cache_only_worker(db_path: str) -> GarminIngestWorker:
    """Build a worker whose body composition lookups are cache-only.

    The bound ``collect_body_composition_data`` method is replaced with a
    cache-only reader so that ``_calculate_median_weight`` never triggers a
    Garmin Connect API request during backfill.
    """
    worker = GarminIngestWorker(db_path=db_path)
    weight_raw_dir = worker.weight_raw_dir

    def _cache_only(date: str) -> dict[str, Any] | None:
        return _load_cached_body_composition(weight_raw_dir, date)

    # Override the bound method on this instance only.
    worker.collect_body_composition_data = _cache_only  # type: ignore[method-assign]
    return worker


def backfill_base_weight(
    db_path: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Backfill NULL ``base_weight_kg`` values and re-evaluate affected form.

    Args:
        db_path: Path to DuckDB database (None resolves via ``$GARMIN_DATA_DIR``).
        dry_run: When True, no DB writes / re-evaluations occur; counts are still
            computed (``updated`` = how many would be updated).

    Returns:
        Dict with keys:
            - ``updated``: activities whose ``base_weight_kg`` was (or would be) set
            - ``skipped``: activities with no resolvable median (left NULL)
            - ``reevaluated``: activities whose form was re-evaluated
            - ``details``: per-activity records
    """
    resolved_db_path = str(get_db_path(db_path))
    worker = _make_cache_only_worker(resolved_db_path)

    # 1. Find activities with NULL base_weight_kg.
    with get_connection(resolved_db_path) as conn:
        rows = conn.execute("""
            SELECT activity_id, activity_date
            FROM activities
            WHERE base_weight_kg IS NULL
            ORDER BY activity_date
            """).fetchall()

    targets = [(int(r[0]), str(r[1])) for r in rows]

    updated = 0
    skipped = 0
    reevaluated = 0
    details: list[dict[str, Any]] = []

    for activity_id, activity_date in targets:
        median = worker._calculate_median_weight(activity_date)

        if not median or median.get("weight_kg") is None:
            skipped += 1
            details.append(
                {
                    "activity_id": activity_id,
                    "activity_date": activity_date,
                    "status": "skipped",
                    "reason": "no_body_composition_in_window",
                }
            )
            continue

        weight_kg = float(median["weight_kg"])
        updated += 1

        if dry_run:
            details.append(
                {
                    "activity_id": activity_id,
                    "activity_date": activity_date,
                    "status": "would_update",
                    "base_weight_kg": weight_kg,
                }
            )
            continue

        # 2. Persist the recomputed base weight.
        with get_write_connection(resolved_db_path) as conn:
            conn.execute(
                "UPDATE activities SET base_weight_kg = ? WHERE activity_id = ?",
                [weight_kg, activity_id],
            )

        record: dict[str, Any] = {
            "activity_id": activity_id,
            "activity_date": activity_date,
            "status": "updated",
            "base_weight_kg": weight_kg,
        }

        # 3. Re-evaluate form so power_* / integrated_score pick up the weight.
        try:
            result = evaluate_and_store(
                activity_id=activity_id,
                activity_date=activity_date,
                db_path=resolved_db_path,
                condition_group="flat_road",
            )
            reevaluated += 1
            record["reevaluated"] = True
            record["power_avg_w"] = result.get("power", {}).get("avg_w")
        except Exception as e:  # noqa: BLE001 - log + continue per activity
            record["reevaluated"] = False
            record["reeval_error"] = str(e)
            print(
                f"Re-evaluation failed for {activity_id} ({activity_date}): {e}",
                file=sys.stderr,
            )

        details.append(record)

    return {
        "updated": updated,
        "skipped": skipped,
        "reevaluated": reevaluated,
        "details": details,
    }


def main() -> int:
    """CLI entry point. Emits a single-line JSON summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Backfill NULL base_weight_kg and re-evaluate affected form."
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

    result = backfill_base_weight(db_path=args.db_path, dry_run=args.dry_run)
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
