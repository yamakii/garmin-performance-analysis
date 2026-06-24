"""Daily wellness range ingest: fill missing days in a window.

Iterates day-by-day over ``[start, end]`` and reuses the single-day,
cache-first collector :func:`collect_wellness_data` (which reads
``raw/wellness/{date}.json`` and only calls the four Garmin endpoints on a
cache miss). Each day with actual wellness data is upserted into
``daily_wellness`` via :meth:`GarminDBWriter.insert_daily_wellness` (issue
#498).

This is the catch-up primitive that backfills RHR / HRV / sleep / training
readiness / body battery / stress for arbitrary date ranges, independently of
activity ingest. It mirrors :mod:`garmin_mcp.ingest.weight_ingest`.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.raw_data_fetcher import collect_wellness_data
from garmin_mcp.utils.paths import get_wellness_raw_dir

logger = logging.getLogger(__name__)


def ingest_wellness_range(
    start_date: str,
    end_date: str,
    db_path: str | None = None,
    throttle_seconds: float = 1.0,
) -> dict[str, Any]:
    """Ingest daily wellness for each day in ``[start_date, end_date]``.

    For every day in the inclusive window, :func:`collect_wellness_data` is
    called (cache-first: a present ``raw/wellness/{date}.json`` avoids any API
    call). Days that yield actual wellness data are upserted into
    ``daily_wellness``.

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``).
        end_date: Inclusive window end (``YYYY-MM-DD``).
        db_path: Optional DuckDB path (defaults to the configured database).
        throttle_seconds: Sleep between *Garmin API calls* (cache misses) to
            avoid rate limiting. No sleep occurs for cache hits.

    Returns:
        Dict ``{"ingested_days": int, "with_data": int, "dates": list[str]}``.
        ``ingested_days`` counts every day in the window; ``with_data`` counts
        only days that had actual wellness data (empty marker days excluded);
        ``dates`` lists each processed day (``YYYY-MM-DD``).
    """
    resolved_path = str(get_db_path(db_path))
    writer = GarminDBWriter(db_path=resolved_path)
    wellness_raw_dir = get_wellness_raw_dir()

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    dates: list[str] = []
    with_data = 0
    pending_throttle = False

    current = start
    while current <= end:
        date_str = current.isoformat()
        cache_hit = (wellness_raw_dir / f"{date_str}.json").exists()

        # Throttle only between actual Garmin API calls (cache misses).
        if pending_throttle and not cache_hit and throttle_seconds > 0:
            time.sleep(throttle_seconds)

        raw_data = collect_wellness_data(wellness_raw_dir, date_str)

        if raw_data and writer.insert_daily_wellness(
            date=date_str, wellness_data=raw_data
        ):
            with_data += 1

        dates.append(date_str)
        if not cache_hit:
            pending_throttle = True
        current += timedelta(days=1)

    logger.info(
        "ingest_wellness_range %s..%s: %d days, %d with data",
        start_date,
        end_date,
        len(dates),
        with_data,
    )

    return {
        "ingested_days": len(dates),
        "with_data": with_data,
        "dates": dates,
    }
