#!/usr/bin/env python3
"""Rate-limit-safe full-history backfill for the ``daily_wellness`` table.

A one-shot batch runner that sits thinly on top of
:func:`garmin_mcp.ingest.wellness_ingest.ingest_wellness_range` (#498) and walks
the entire available history (back to device ownership) **without tripping the
Garmin API rate limit**.

Role split vs. ``catch_up`` (#508):

- ``catch_up`` wellness: daily differential follow-up + small manual gap fills
  (default throttle 1s).
- ``backfill_wellness`` (this module): full-history one-shot pull with a
  conservative throttle + jitter, exponential 429 backoff, automatic data-floor
  stop, monthly chunking, and resume-on-rerun (cache-first).

Design (rate-limit non-contact):

- One wellness day fires 4 endpoints; empirically 4 calls / 8s (avg ~0.5 call/s)
  stays inside the proven envelope (521 Run backfill at 8s spacing succeeded).
- Default throttle 8s/day + +/-20% jitter to avoid lockstep.
- Monthly chunks processed **newest -> oldest**.
- Auto data-floor stop: when ``--start-date`` is omitted, two consecutive
  ``with_data == 0`` chunks are treated as reaching the floor (avoids hammering
  pre-ownership dates; 2 consecutive guards against a single missing month).
- Exponential 429 backoff: 60 -> 120 -> 240 -> 480 -> 600s (cap), up to
  ``max_retries`` attempts, then a clean abort (state persists in cache, so a
  re-run resumes for free).

Usage:
    uv run python -m garmin_mcp.scripts.backfill_wellness
    uv run python -m garmin_mcp.scripts.backfill_wellness --start-date 2024-01-01
    uv run python -m garmin_mcp.scripts.backfill_wellness --throttle 8.0 --jitter 0.2
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import random
import sys
import time
from datetime import date
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.ingest.retry import backoff_seconds, is_rate_limit_error, jittered

logger = logging.getLogger(__name__)


def month_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Split ``[start, end]`` into monthly ``(chunk_start, chunk_end)`` pairs.

    Returned newest -> oldest. Calendar-month boundaries are used, but the first
    and last chunks are clamped to the requested window edges.

    Args:
        start: Inclusive window start (``YYYY-MM-DD``).
        end: Inclusive window end (``YYYY-MM-DD``).

    Returns:
        List of ``(chunk_start, chunk_end)`` tuples (``YYYY-MM-DD``), ordered
        from the most recent month to the oldest. Empty if ``start > end``.
    """
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    if start_d > end_d:
        return []

    chunks: list[tuple[str, str]] = []
    # Walk month by month from oldest to newest, then reverse.
    cursor = date(start_d.year, start_d.month, 1)
    while cursor <= end_d:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_first = date(cursor.year, cursor.month, 1)
        month_last = date(cursor.year, cursor.month, last_day)

        chunk_start = max(month_first, start_d)
        chunk_end = min(month_last, end_d)
        chunks.append((chunk_start.isoformat(), chunk_end.isoformat()))

        # Advance to the first day of the next month.
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    chunks.reverse()
    return chunks


def _ingest_chunk_with_retry(
    chunk_start: str,
    chunk_end: str,
    *,
    throttle: float,
    jitter: float,
    max_retries: int,
    max_backoff: float,
    db_path: str | None,
    sleep: Any,
    rand: Any,
) -> dict[str, Any] | None:
    """Ingest one chunk, retrying on rate-limit errors with exponential backoff.

    Returns the ingest result dict on success, or ``None`` when the retry budget
    is exhausted (signalling the caller to abort cleanly).
    """
    from garmin_mcp.ingest.wellness_ingest import ingest_wellness_range

    throttle_seconds = jittered(throttle, jitter, rand())
    for attempt in range(max_retries + 1):
        try:
            return ingest_wellness_range(
                chunk_start,
                chunk_end,
                db_path=db_path,
                throttle_seconds=throttle_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - classify then re-raise non-429
            if not is_rate_limit_error(exc):
                raise
            if attempt >= max_retries:
                logger.warning(
                    "backfill_wellness: rate-limited on %s..%s, retries exhausted",
                    chunk_start,
                    chunk_end,
                )
                return None
            delay = backoff_seconds(attempt, cap=max_backoff)
            logger.warning(
                "backfill_wellness: rate-limited on %s..%s, "
                "backing off %.0fs (attempt %d/%d)",
                chunk_start,
                chunk_end,
                delay,
                attempt + 1,
                max_retries,
            )
            sleep(delay)
    return None


def run_backfill(
    start_date: str | None,
    end_date: str | None,
    *,
    throttle: float = 8.0,
    jitter: float = 0.2,
    stop_after_empty_chunks: int = 2,
    max_retries: int = 5,
    max_backoff: float = 600.0,
    db_path: str | None = None,
    sleep: Any = time.sleep,
    rand: Any = random.random,
) -> dict[str, Any]:
    """Backfill ``daily_wellness`` over monthly chunks, newest -> oldest.

    Iterates monthly chunks. When ``start_date`` is omitted, stops after
    ``stop_after_empty_chunks`` consecutive ``with_data == 0`` chunks (data-floor
    auto-stop). Rate-limit errors trigger exponential backoff; exhausting
    ``max_retries`` aborts cleanly (no exception). Cache-first ingest makes
    re-runs resume for free.

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``), or ``None`` to
            auto-recede to the data floor.
        end_date: Inclusive window end (``YYYY-MM-DD``), or ``None`` for today.
        throttle: Per-day throttle (seconds) passed to the ingest primitive.
        jitter: Jitter fraction applied to ``throttle`` per chunk.
        stop_after_empty_chunks: Consecutive empty chunks that trigger the
            data-floor auto-stop (only when ``start_date`` is omitted).
        max_retries: Max rate-limit retries per chunk before aborting.
        max_backoff: Backoff cap (seconds).
        db_path: Optional DuckDB path (defaults to the configured database).
        sleep: Injectable sleep function (for tests).
        rand: Injectable ``[0, 1)`` random source (for tests).

    Returns:
        Dict with keys ``chunks`` (processed count), ``ingested_days`` (total
        days processed), ``with_data`` (days with actual data), ``floor_date``
        (oldest chunk start reached, or ``None``), and ``aborted_reason``
        (``"rate_limited"`` or ``None``).
    """
    resolved_db_path = str(get_db_path(db_path))
    resolved_end = end_date if end_date is not None else date.today().isoformat()
    auto_floor = start_date is None
    # When start_date is omitted, recede far back; the floor auto-stop ends it.
    resolved_start = start_date if start_date is not None else "2010-01-01"

    chunks = month_chunks(resolved_start, resolved_end)

    processed = 0
    total_days = 0
    total_with_data = 0
    floor_date: str | None = None
    aborted_reason: str | None = None
    consecutive_empty = 0

    for chunk_start, chunk_end in chunks:
        result = _ingest_chunk_with_retry(
            chunk_start,
            chunk_end,
            throttle=throttle,
            jitter=jitter,
            max_retries=max_retries,
            max_backoff=max_backoff,
            db_path=resolved_db_path,
            sleep=sleep,
            rand=rand,
        )
        if result is None:
            aborted_reason = "rate_limited"
            break

        processed += 1
        floor_date = chunk_start
        total_days += int(result.get("ingested_days", 0))
        chunk_with_data = int(result.get("with_data", 0))
        total_with_data += chunk_with_data

        if auto_floor:
            if chunk_with_data == 0:
                consecutive_empty += 1
                if consecutive_empty >= stop_after_empty_chunks:
                    logger.info(
                        "backfill_wellness: data floor reached after %d empty "
                        "chunks (floor=%s)",
                        consecutive_empty,
                        chunk_start,
                    )
                    break
            else:
                consecutive_empty = 0

    return {
        "chunks": processed,
        "ingested_days": total_days,
        "with_data": total_with_data,
        "floor_date": floor_date,
        "aborted_reason": aborted_reason,
    }


def main() -> int:
    """CLI entry point. Emits a single-line JSON summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Rate-limit-safe full-history backfill of daily_wellness."
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Inclusive start (YYYY-MM-DD). Omit to auto-recede to data floor.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Inclusive end (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=8.0,
        help="Per-day throttle in seconds (default: 8.0).",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.2,
        help="Jitter fraction applied to throttle (default: 0.2 = +/-20%%).",
    )
    parser.add_argument(
        "--stop-after-empty-chunks",
        type=int,
        default=2,
        help="Consecutive empty chunks triggering data-floor stop (default: 2).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Max rate-limit retries per chunk before aborting (default: 5).",
    )
    parser.add_argument(
        "--max-backoff",
        type=float,
        default=600.0,
        help="Backoff cap in seconds (default: 600).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to DuckDB database (default: $GARMIN_DATA_DIR/database/...)",
    )
    args = parser.parse_args()

    result = run_backfill(
        args.start_date,
        args.end_date,
        throttle=args.throttle,
        jitter=args.jitter,
        stop_after_empty_chunks=args.stop_after_empty_chunks,
        max_retries=args.max_retries,
        max_backoff=args.max_backoff,
        db_path=args.db_path,
    )
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
