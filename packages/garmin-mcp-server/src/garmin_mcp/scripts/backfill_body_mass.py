#!/usr/bin/env python3
"""Backfill ``activities.body_mass_kg`` from the ``body_composition`` table.

For each activity, find the ``body_composition.weight_kg`` whose measurement
``date`` is *nearest* (before or after) the ``activities.activity_date``, within
``window_days`` days, and set ``activities.body_mass_kg`` to it. Ties on the
absolute day difference are broken toward the more recent measurement.

Why this exists (issue #528):
    The original ``phase0_power_prep`` migration populated ``body_mass_kg`` once,
    when ``body_composition`` was nearly empty. Migrations only run once, so
    later body-composition backfills never re-populated ``body_mass_kg``. This
    script is **re-runnable**: it can be invoked any time ``body_composition``
    grows to refresh the join.

Window semantics:
    - Nearest measurement within ``+/- window_days`` (before OR after the
      activity date), minimizing ``|day difference|``.
    - Activities with no measurement inside the window are left ``NULL``.
    - This differs from the migration's unbounded "<= date" rule: a windowed
      nearest match better reflects "the athlete's weight at the time of the
      activity" and avoids stamping a years-old measurement onto a recent run.

force semantics:
    - ``force=False`` (default): only update rows where ``body_mass_kg IS NULL``.
    - ``force=True``: recompute ALL rows (may overwrite an existing value, and
      may set ``NULL`` if no measurement falls inside the window).

Usage:
    uv run python -m garmin_mcp.scripts.backfill_body_mass
    uv run python -m garmin_mcp.scripts.backfill_body_mass --window-days 14
    uv run python -m garmin_mcp.scripts.backfill_body_mass --force
    uv run python -m garmin_mcp.scripts.backfill_body_mass --dry-run
    uv run python -m garmin_mcp.scripts.backfill_body_mass --db-path /path/to.duckdb
"""

from __future__ import annotations

import argparse
import json
import sys

from garmin_mcp.database.connection import get_db_path, get_write_connection

# Correlated subquery selecting the nearest body_composition measurement within
# +/- window_days of the activity date. Ordering by absolute day difference picks
# the closest; the secondary ``bc.date DESC`` breaks ties toward the more recent
# measurement. The ``?`` placeholder is the window in days.
_NEAREST_SUBQUERY = """
    SELECT bc.weight_kg
    FROM body_composition bc
    WHERE bc.weight_kg IS NOT NULL
      AND abs(date_diff('day', bc.date, a.activity_date)) <= ?
    ORDER BY abs(date_diff('day', bc.date, a.activity_date)) ASC, bc.date DESC
    LIMIT 1
"""


def backfill_body_mass(
    db_path: str | None = None,
    window_days: int = 30,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Backfill ``activities.body_mass_kg`` from ``body_composition``.

    For each activity, set ``body_mass_kg`` to the nearest
    ``body_composition.weight_kg`` within ``+/- window_days`` of the activity
    date (ties broken toward the more recent measurement). Activities without a
    measurement inside the window are left ``NULL``.

    Args:
        db_path: Path to DuckDB database (None resolves via ``$GARMIN_DATA_DIR``).
        window_days: Maximum absolute day difference between the activity date
            and the body-composition measurement date.
        force: When False, only rows where ``body_mass_kg IS NULL`` are updated.
            When True, all rows are recomputed (may overwrite or set ``NULL``).
        dry_run: When True, the counts are still computed but no UPDATE is
            committed. ``populated`` / ``still_null`` reflect what *would* result
            from the update.

    Returns:
        Dict with keys:
            - ``total``: number of activities
            - ``populated``: activities with ``body_mass_kg`` NOT NULL (after)
            - ``still_null``: activities with ``body_mass_kg`` NULL (after)
    """
    resolved_db_path = str(get_db_path(db_path))

    where_clause = "" if force else "WHERE a.body_mass_kg IS NULL"
    update_sql = f"""
        UPDATE activities AS a
        SET body_mass_kg = (
            {_NEAREST_SUBQUERY}
        )
        {where_clause}
    """

    with get_write_connection(resolved_db_path) as conn:
        total = _scalar(conn.execute("SELECT COUNT(*) FROM activities").fetchone())

        if dry_run:
            # Compute the post-update population without persisting. A correlated
            # subquery yields the value each row *would* receive; rows excluded by
            # the WHERE clause keep their current value.
            populated = _scalar(
                conn.execute(
                    f"""
                    SELECT COUNT(*) FROM (
                        SELECT
                            CASE
                                WHEN {"TRUE" if force else "a.body_mass_kg IS NULL"}
                                THEN ({_NEAREST_SUBQUERY})
                                ELSE a.body_mass_kg
                            END AS new_value
                        FROM activities AS a
                    )
                    WHERE new_value IS NOT NULL
                    """,
                    [window_days],
                ).fetchone()
            )
        else:
            conn.execute(update_sql, [window_days])
            populated = _scalar(
                conn.execute(
                    "SELECT COUNT(*) FROM activities WHERE body_mass_kg IS NOT NULL"
                ).fetchone()
            )

    return {
        "total": total,
        "populated": populated,
        "still_null": total - populated,
    }


def _scalar(row: tuple | None) -> int:
    """Return the first column of a COUNT(*) row as an int (0 if missing)."""
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def main() -> int:
    """CLI entry point. Prints a summary and a single-line JSON result."""
    parser = argparse.ArgumentParser(
        description=(
            "Backfill activities.body_mass_kg from body_composition "
            "(nearest measurement within a date window)."
        )
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to DuckDB database (default: $GARMIN_DATA_DIR/database/...)",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Max abs day difference to a body_composition measurement (default 30).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute all rows (default: only rows where body_mass_kg IS NULL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute counts without committing the UPDATE.",
    )
    args = parser.parse_args()

    result = backfill_body_mass(
        db_path=args.db_path,
        window_days=args.window_days,
        force=args.force,
        dry_run=args.dry_run,
    )

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}body_mass_kg populated: "
        f"{result['populated']}/{result['total']} activities "
        f"(still_null={result['still_null']})"
    )
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
