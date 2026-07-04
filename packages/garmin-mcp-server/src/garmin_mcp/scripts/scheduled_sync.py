"""Scheduled auto-sync entrypoint: catch-up ingest across all domains + log it.

Runs :func:`catch_up_ingest` over every domain (running / weight / strength /
wellness) and records a single row in the ``sync_runs`` table describing the
run's window of domains, the full result payload, and an overall status. This
makes the previously manual catch-up/backfill flows callable unattended from a
cron job or systemd timer, leaving an auditable trail (issue #712, parent #701).

The per-domain watermark resolution is inherited from ``catch_up_ingest``: each
domain resolves its own ``[start, end]`` window from its latest stored date
(``ingest/catch_up.py``), so this entrypoint stays a thin orchestrator.

Trend-pending detection also lives in ``catch_up_ingest`` (issue #810): on a
fully-successful run it attaches a ``trend_pending`` descriptor for the last
completed week still missing a narration. This entrypoint simply records
whatever ``catch_up_ingest`` returns, so ``trend_pending`` is persisted in the
``sync_runs`` row unchanged for a cron/manual runner to fire ``trend-narration``.

Status semantics:

- ``success`` — every requested domain returned a result payload.
- ``partial`` — at least one domain returned ``{"error": ...}`` (the others
  still completed; the error is preserved in the recorded ``results`` JSON).
- ``error``   — the run itself raised before/while producing results.

Usage::

    uv run --directory packages/garmin-mcp-server \
      python -m garmin_mcp.scripts.scheduled_sync

    # Restrict to specific domains
    uv run python -m garmin_mcp.scripts.scheduled_sync --domains wellness,running
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from typing import Any

from garmin_mcp.database.connection import get_db_path, get_write_connection
from garmin_mcp.database.migrations.runner import ensure_schema_current
from garmin_mcp.ingest.catch_up import DEFAULT_DOMAINS, catch_up_ingest

logger = logging.getLogger(__name__)


def _classify_status(results: dict[str, Any]) -> str:
    """Return ``"success"`` unless any domain entry carries an ``error`` key.

    The ``"window"`` key (resolved windows, not a domain result) is ignored.
    """
    domain_results = {k: v for k, v in results.items() if k != "window"}
    has_error = any(
        isinstance(value, dict) and "error" in value
        for value in domain_results.values()
    )
    return "partial" if has_error else "success"


def _record_run(
    db_path: str,
    started_at: datetime,
    finished_at: datetime,
    domains: list[str],
    results: dict[str, Any],
    status: str,
) -> int:
    """Insert one row into ``sync_runs`` and return its ``run_id``."""
    with get_write_connection(db_path) as conn:
        row = conn.execute("SELECT nextval('seq_sync_runs_id')").fetchone()
        assert row is not None
        run_id = int(row[0])
        conn.execute(
            """
            INSERT INTO sync_runs (
                run_id, started_at, finished_at, domains, results, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                started_at,
                finished_at,
                ",".join(domains),
                json.dumps(results, default=str),
                status,
            ],
        )
    return run_id


def run_sync(
    domains: list[str] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Run ``catch_up_ingest`` across all domains and log the run to ``sync_runs``.

    Args:
        domains: Optional subset of ``["running", "weight", "strength",
            "wellness"]``. ``None`` runs all four (the catch-up default).
        db_path: Optional DuckDB path (defaults to the configured database).

    Returns:
        ``{"status": "success"|"partial"|"error", "results": {...},
        "run_id": int}``. ``status`` is ``"partial"`` when any domain returned
        ``{"error": ...}``, and ``"error"`` when the run itself raised. On a
        fully-successful run ``results`` may carry a ``"trend_pending"``
        descriptor (attached by ``catch_up_ingest``) for the last completed week
        still missing a trend narration.
    """
    resolved_path = str(get_db_path(db_path))
    resolved_domains = list(domains) if domains is not None else list(DEFAULT_DOMAINS)

    # Guarantee the sync_runs table exists (safe/no-op when already current).
    ensure_schema_current(resolved_path)

    started_at = datetime.now()
    try:
        results = catch_up_ingest(domains=resolved_domains, db_path=resolved_path)
        status = _classify_status(results)
    except Exception as exc:  # noqa: BLE001 - record the failure, do not crash cron
        logger.exception("scheduled sync failed")
        results = {"error": str(exc)}
        status = "error"

    finished_at = datetime.now()

    run_id = _record_run(
        resolved_path, started_at, finished_at, resolved_domains, results, status
    )
    return {"status": status, "results": results, "run_id": run_id}


def main() -> int:
    """CLI entrypoint. Returns 0 on ``success``, 1 otherwise (partial/error)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domains",
        default=None,
        help=(
            "Comma-separated subset of running,weight,strength,wellness "
            "(default: all four)."
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Explicit DuckDB path (default: configured database).",
    )
    args = parser.parse_args()

    domains = args.domains.split(",") if args.domains else None
    outcome = run_sync(domains=domains, db_path=args.db_path)
    print(json.dumps(outcome, default=str))
    return 0 if outcome["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
