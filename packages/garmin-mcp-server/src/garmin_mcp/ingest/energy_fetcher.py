"""Daily energy (intake / expenditure) fetcher that re-fetches until a day settles.

The daily user summary (``client.get_user_summary(date)``) carries the day's
energy expenditure (total / active / BMR kcal) and -- when MyFitnessPal is
linked -- the food intake (``consumedKilocalories``). Both keep moving long
after the day starts: the current day is only partially covered, and the
athlete may log or correct food days later. So unlike the other raw caches,
an energy file is **not** authoritative on first write:

- Every date is re-fetched until ``fetched_at >= date + SETTLE_DAYS``; after
  that the cached snapshot is trusted and the API is not called again (the
  same grace idea as ``raw_data_fetcher._marker_is_authoritative``).
- The raw file ``raw/energy/{date}.json`` keeps the first and latest fetch
  time, the latest summary, and a revision history: a revision is appended
  only when ``consumedKilocalories`` changed. The history cannot be
  re-fetched, so writes are atomic (temp file + ``os.replace``).
- An API error returns the cached dict unchanged and writes nothing.

Timestamps are local naive ISO strings (``YYYY-MM-DDTHH:MM:SS``), the same
convention as ``_marker_is_authoritative`` (which compares a local mtime).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date as dt_date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from garmin_mcp.ingest.api_client import get_garmin_client
from garmin_mcp.ingest.retry import call_with_retry

logger = logging.getLogger(__name__)

SETTLE_DAYS: int = 7
FULL_DAY_SECONDS: int = 86_400


def _parse_ts(value: Any) -> datetime | None:
    """Parse a stored ISO timestamp, returning ``None`` when absent/invalid."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _coverage_seconds(summary: dict[str, Any] | None) -> int | None:
    """Return the summary's covered duration in whole seconds (or ``None``)."""
    if not isinstance(summary, dict):
        return None
    millis = summary.get("durationInMilliseconds")
    if millis is None:
        return None
    try:
        return int(millis) // 1000
    except (TypeError, ValueError):
        return None


def _energy_cache_is_settled(
    snapshot: dict[str, Any], target_date: dt_date, settle_days: int = SETTLE_DAYS
) -> bool:
    """Return True when a cached energy snapshot can be trusted as final.

    A snapshot is settled once its latest fetch happened at least
    ``settle_days`` after the start of ``target_date``: by then the day's
    coverage is complete and late intake edits have had time to land.

    Args:
        snapshot: Cached raw energy dict (needs ``fetched_at``).
        target_date: The day the snapshot describes.
        settle_days: Days after ``target_date`` before the cache is final.

    Returns:
        ``True`` when the cache is authoritative (skip re-fetch), else
        ``False`` (including a missing or unparseable ``fetched_at``).
    """
    fetched_at = _parse_ts(snapshot.get("fetched_at"))
    if fetched_at is None:
        return False
    settle_at = datetime.combine(target_date, datetime.min.time()) + timedelta(
        days=settle_days
    )
    return fetched_at >= settle_at


def _load_cached(energy_file: Path) -> dict[str, Any] | None:
    """Read a cached raw energy file, or ``None`` when absent/unreadable."""
    if not energy_file.exists():
        return None
    try:
        with open(energy_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        logger.warning(f"Unreadable energy cache {energy_file}: {exc}")
        return None
    return data if isinstance(data, dict) and data else None


def energy_needs_fetch(energy_raw_dir: Path, date: str) -> bool:
    """Return True when :func:`collect_energy_data` would call the API."""
    cached = _load_cached(energy_raw_dir / f"{date}.json")
    if cached is None:
        return True
    return not _energy_cache_is_settled(cached, dt_date.fromisoformat(date))


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to ``path`` via a temp file + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def collect_energy_data(
    energy_raw_dir: Path, date: str, now: datetime | None = None
) -> dict[str, Any] | None:
    """Collect the daily energy snapshot, re-fetching until the day settles.

    Args:
        energy_raw_dir: Energy raw data directory (``raw/energy``).
        date: Date in ``YYYY-MM-DD`` format.
        now: Injectable local naive "now" (defaults to ``datetime.now()``).

    Returns:
        The raw energy dict ``{fetched_at, first_fetched_at, summary,
        revisions}``; the cached dict when settled or when the API failed; or
        ``None`` when there is neither a cache nor a usable API response.
    """
    energy_file = energy_raw_dir / f"{date}.json"
    cached = _load_cached(energy_file)
    target = dt_date.fromisoformat(date)

    if cached is not None and _energy_cache_is_settled(cached, target):
        logger.debug(f"Energy cache for {date} is settled; skipping API call")
        return cached

    current = (now or datetime.now()).replace(microsecond=0)

    try:
        client = get_garmin_client()
        summary = call_with_retry(client.get_user_summary, date)
    except Exception as exc:  # noqa: BLE001 - keep the cache on any API error
        # A failed call is not "no data": write nothing so the next run
        # re-fetches, and keep serving whatever was cached.
        logger.error(f"Error fetching energy data for {date}: {exc}")
        return cached

    if not isinstance(summary, dict) or not summary:
        logger.warning(f"No user summary returned for {date}")
        return cached

    fetched_at = current.isoformat()
    previous = cached or {}
    previous_summary = previous.get("summary")
    revisions: list[dict[str, Any]] = list(previous.get("revisions") or [])

    consumed = summary.get("consumedKilocalories")
    coverage = _coverage_seconds(summary)
    if not revisions or revisions[-1].get("consumed_kcal") != consumed:
        revisions.append(
            {
                "fetched_at": fetched_at,
                "coverage_seconds": coverage,
                "consumed_kcal": consumed,
                # Coverage of the fetch this one replaced: a revision only
                # counts as post-close when BOTH fetches covered the full day.
                "previous_coverage_seconds": _coverage_seconds(previous_summary),
            }
        )

    snapshot: dict[str, Any] = {
        "fetched_at": fetched_at,
        "first_fetched_at": previous.get("first_fetched_at") or fetched_at,
        "summary": summary,
        "revisions": revisions,
    }
    _write_atomic(energy_file, snapshot)
    logger.info(f"Cached energy data to {energy_file}")
    return snapshot
