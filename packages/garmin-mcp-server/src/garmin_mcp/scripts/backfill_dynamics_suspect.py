#!/usr/bin/env python3
"""Backfill ``splits.dynamics_suspect`` for pod runs already in DuckDB (#1635).

New runs are flagged at ingest. This applies the same detection
(``form_baseline.dynamics_quality.flag_suspect_dynamics``) to the runs that
were ingested before migration 39. It never deletes a row and is idempotent:
every run's flags are rewritten from scratch.

``--dry-run`` runs the detection inside a transaction and rolls it back, so it
lists what would be flagged without changing the database.

Order after the merge: reload the server, run this, retrain the pod baseline
(``backfill_baseline_history --dynamics-source pod``), then re-evaluate the pod
runs.

Usage:
    uv run python -m garmin_mcp.scripts.backfill_dynamics_suspect --dry-run
    uv run python -m garmin_mcp.scripts.backfill_dynamics_suspect --start-date 2026-10-01
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from garmin_mcp.database.connection import get_db_path, get_write_connection
from garmin_mcp.form_baseline.dynamics_quality import flag_suspect_dynamics


def backfill_dynamics_suspect(
    db_path: str | None = None,
    start_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Flag suspect pod splits for every pod run from ``start_date``.

    Args:
        db_path: Path to DuckDB database. None uses the configured default.
        start_date: Only runs on or after this date (YYYY-MM-DD) are rewritten.
        dry_run: Detect and report, then roll back.

    Returns:
        Summary with the per-run listing of flagged runs and the totals.
    """
    resolved = str(get_db_path(db_path))
    flagged_runs: list[dict[str, Any]] = []
    scanned = 0

    with get_write_connection(resolved) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            query = (
                "SELECT activity_id, activity_date FROM activities "
                "WHERE dynamics_source = 'pod'"
            )
            params: list[Any] = []
            if start_date:
                query += " AND activity_date >= ?"
                params.append(start_date)
            query += " ORDER BY activity_date, activity_id"
            for activity_id, activity_date in conn.execute(query, params).fetchall():
                scanned += 1
                count = flag_suspect_dynamics(conn, int(activity_id))
                if count:
                    flagged_runs.append(
                        {
                            "activity_id": int(activity_id),
                            "date": str(activity_date),
                            "flagged_splits": count,
                        }
                    )
            conn.execute("ROLLBACK" if dry_run else "COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return {
        "pod_runs_scanned": scanned,
        "runs_flagged": len(flagged_runs),
        "splits_flagged": sum(run["flagged_splits"] for run in flagged_runs),
        "runs": flagged_runs,
        "dry_run": dry_run,
    }


def main() -> int:
    """CLI entry point. Prints a per-run listing, then a JSON summary."""
    parser = argparse.ArgumentParser(
        description="Flag collapsed pod-dynamics splits (splits.dynamics_suspect)."
    )
    parser.add_argument("--db-path", default=None, help="Path to DuckDB database.")
    parser.add_argument(
        "--start-date", default=None, help="Only runs on or after YYYY-MM-DD."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be flagged without writing.",
    )
    args = parser.parse_args()

    result = backfill_dynamics_suspect(
        db_path=args.db_path, start_date=args.start_date, dry_run=args.dry_run
    )
    for run in result["runs"]:
        print(f"{run['date']}  {run['activity_id']}  {run['flagged_splits']} splits")
    summary = {key: value for key, value in result.items() if key != "runs"}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
