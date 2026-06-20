"""Weight (body composition) range ingest: fill missing days in a window.

Iterates day-by-day over ``[start, end]`` and reuses the existing single-day,
cache-first collector :func:`collect_body_composition_data` (which reads
``raw/weight/{date}.json`` and only calls ``get_daily_weigh_ins`` on a cache
miss). Each day with actual weight data is upserted into ``body_composition``
via :meth:`GarminDBWriter.insert_body_composition` (issue #461).

This is the catch-up primitive that backfills weight for arbitrary date ranges
independently of activity ingest (which only fetches the day of each run).
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.raw_data_fetcher import collect_body_composition_data
from garmin_mcp.utils.paths import get_weight_raw_dir

logger = logging.getLogger(__name__)


def ingest_weight_range(
    start_date: str,
    end_date: str,
    db_path: str | None = None,
    throttle_seconds: float = 1.0,
) -> dict[str, Any]:
    """Ingest body composition for each day in ``[start_date, end_date]``.

    For every day in the inclusive window, :func:`collect_body_composition_data`
    is called (cache-first: a present ``raw/weight/{date}.json`` avoids any API
    call). Days that yield actual weight data are upserted into
    ``body_composition``.

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``).
        end_date: Inclusive window end (``YYYY-MM-DD``).
        db_path: Optional DuckDB path (defaults to the configured database).
        throttle_seconds: Sleep between *Garmin API calls* (cache misses) to
            avoid rate limiting. No sleep occurs for cache hits.

    Returns:
        Dict ``{"ingested_days": int, "with_data": int, "dates": list[str]}``.
        ``ingested_days`` counts every day in the window; ``with_data`` counts
        only days that had actual weight data (empty marker days excluded);
        ``dates`` lists each processed day (``YYYY-MM-DD``).
    """
    resolved_path = str(get_db_path(db_path))
    writer = GarminDBWriter(db_path=resolved_path)
    weight_raw_dir = get_weight_raw_dir()

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    dates: list[str] = []
    with_data = 0
    pending_throttle = False

    current = start
    while current <= end:
        date_str = current.isoformat()
        cache_hit = (weight_raw_dir / f"{date_str}.json").exists()

        # Throttle only between actual Garmin API calls (cache misses).
        if pending_throttle and not cache_hit and throttle_seconds > 0:
            time.sleep(throttle_seconds)

        raw_data = collect_body_composition_data(weight_raw_dir, date_str)

        if raw_data and raw_data.get("dateWeightList"):
            writer.insert_body_composition(date=date_str, weight_data=raw_data)
            with_data += 1

        dates.append(date_str)
        if not cache_hit:
            pending_throttle = True
        current += timedelta(days=1)

    logger.info(
        "ingest_weight_range %s..%s: %d days, %d with data",
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
