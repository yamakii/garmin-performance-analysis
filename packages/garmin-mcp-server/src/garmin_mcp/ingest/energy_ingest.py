"""Daily energy range ingest: (re-)fetch each day until it settles.

Iterates day-by-day over ``[start, end]`` and calls
:func:`garmin_mcp.ingest.energy_fetcher.collect_energy_data`, which re-fetches
a day from Garmin until its cache is ``SETTLE_DAYS`` old and serves the cache
afterwards. Every day with a summary is upserted into ``daily_energy`` via
:meth:`GarminDBWriter.insert_daily_energy` (issue #1433). Mirrors
:mod:`garmin_mcp.ingest.wellness_ingest`.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.ingest.energy_fetcher import collect_energy_data, energy_needs_fetch
from garmin_mcp.utils.paths import get_energy_raw_dir

logger = logging.getLogger(__name__)


def ingest_energy_range(
    start_date: str,
    end_date: str,
    db_path: str | None = None,
    throttle_seconds: float = 1.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ingest daily energy for each day in ``[start_date, end_date]``.

    Args:
        start_date: Inclusive window start (``YYYY-MM-DD``).
        end_date: Inclusive window end (``YYYY-MM-DD``).
        db_path: Optional DuckDB path (defaults to the configured database).
        throttle_seconds: Sleep between *Garmin API calls* to avoid rate
            limiting. No sleep occurs for settled (cache-served) days.
        now: Injectable local naive "now" passed to the fetcher.

    Returns:
        Dict ``{"ingested_days": int, "with_intake": int, "dates": list[str]}``.
        ``ingested_days`` counts every day in the window; ``with_intake``
        counts days whose stored row carries a positive ``consumed_kcal``;
        ``dates`` lists each processed day (``YYYY-MM-DD``).
    """
    resolved_path = str(get_db_path(db_path))
    writer = GarminDBWriter(db_path=resolved_path)
    energy_raw_dir = get_energy_raw_dir()

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    dates: list[str] = []
    with_intake = 0
    pending_throttle = False

    current = start
    while current <= end:
        date_str = current.isoformat()
        needs_fetch = energy_needs_fetch(energy_raw_dir, date_str)

        # Throttle only between actual Garmin API calls.
        if pending_throttle and needs_fetch and throttle_seconds > 0:
            time.sleep(throttle_seconds)

        raw = collect_energy_data(energy_raw_dir, date_str, now=now)

        if raw and writer.insert_daily_energy(date=date_str, energy_raw=raw):
            consumed = (raw.get("summary") or {}).get("consumedKilocalories")
            if isinstance(consumed, int | float) and consumed > 0:
                with_intake += 1

        dates.append(date_str)
        if needs_fetch:
            pending_throttle = True
        current += timedelta(days=1)

    logger.info(
        "ingest_energy_range %s..%s: %d days, %d with intake",
        start_date,
        end_date,
        len(dates),
        with_intake,
    )

    return {
        "ingested_days": len(dates),
        "with_intake": with_intake,
        "dates": dates,
    }
