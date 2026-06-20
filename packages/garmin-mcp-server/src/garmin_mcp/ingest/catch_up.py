"""Catch-up ingest orchestrator: fill running/weight/strength gaps in one call.

For each requested domain, resolve an independent ``[start, end]`` window and
delegate to that domain's existing ingest primitive:

- ``running``  -> :func:`ingest_running_activities`
- ``weight``   -> :func:`ingest_weight_range`
- ``strength`` -> :func:`ingest_strength_sessions`

The window is resolved per domain because each table advances at its own pace:

- ``end``           = ``end_date`` or today.
- per-domain start  = ``start_date`` (explicit, shared) or the domain's latest
  stored date (issue #460 readers), or ``end - 30 days`` when that table is
  empty (``_EMPTY_DB_FLOOR_DAYS``).

A failure in one domain does not abort the others: the offending domain's entry
carries an ``error`` string while the remaining domains complete normally.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)

DEFAULT_DOMAINS: tuple[str, ...] = ("running", "weight", "strength")
_EMPTY_DB_FLOOR_DAYS = 30

# Reader method used to find each domain's latest stored date (issue #460).
_LATEST_DATE_METHOD: dict[str, str] = {
    "running": "get_latest_activity_date",
    "weight": "get_latest_weight_date",
    "strength": "get_latest_strength_date",
}


def _resolve_domain_window(
    domain: str,
    start_date: str | None,
    resolved_end: str,
    reader: GarminDBReader,
) -> tuple[str, str]:
    """Resolve the inclusive ``(start, end)`` window for a single domain.

    Args:
        domain: One of ``"running"``, ``"weight"``, ``"strength"``.
        start_date: Explicit shared start (``YYYY-MM-DD``), or ``None`` for
            catch-up resolution from the domain's latest stored date.
        resolved_end: The already-resolved window end (``YYYY-MM-DD``).
        reader: Reader used to query the domain's latest stored date.

    Returns:
        ``(start, end)`` as ``YYYY-MM-DD`` strings. When ``start_date`` is
        omitted: the domain's latest stored date, or ``end - 30 days`` when the
        domain's table is empty.
    """
    if start_date is not None:
        return start_date, resolved_end

    latest_method = getattr(reader, _LATEST_DATE_METHOD[domain])
    latest = latest_method()
    if latest is not None:
        return latest, resolved_end

    floor = date.fromisoformat(resolved_end) - timedelta(days=_EMPTY_DB_FLOOR_DAYS)
    return floor.isoformat(), resolved_end


def _run_running(window_start: str, window_end: str, db_path: str) -> dict[str, Any]:
    from garmin_mcp.ingest.running_ingest import ingest_running_activities

    return ingest_running_activities(window_start, window_end, db_path=db_path)


def _run_weight(window_start: str, window_end: str, db_path: str) -> dict[str, Any]:
    from garmin_mcp.ingest.weight_ingest import ingest_weight_range

    return ingest_weight_range(window_start, window_end, db_path=db_path)


def _run_strength(window_start: str, window_end: str, db_path: str) -> dict[str, Any]:
    from garmin_mcp.ingest.strength_ingest import ingest_strength_sessions

    return ingest_strength_sessions(window_start, window_end, db_path=db_path)


_DOMAIN_RUNNERS = {
    "running": _run_running,
    "weight": _run_weight,
    "strength": _run_strength,
}


def catch_up_ingest(
    start_date: str | None = None,
    end_date: str | None = None,
    domains: list[str] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Differential catch-up ingest across running/weight/strength domains.

    For each requested domain, resolve an independent window and delegate to its
    ingest primitive. The ``end`` is shared (``end_date`` or today); each
    domain's ``start`` is ``start_date`` when given, else that domain's latest
    stored date, else ``end - 30 days``.

    Args:
        start_date: Optional explicit shared window start (``YYYY-MM-DD``). When
            omitted, each domain resolves its own start from its latest date.
        end_date: Optional inclusive window end (``YYYY-MM-DD``). Defaults to
            today when omitted.
        domains: Optional subset of ``["running", "weight", "strength"]``.
            Defaults to all three. Domains not listed are skipped entirely.
        db_path: Optional DuckDB path (defaults to the configured database).

    Returns:
        Dict keyed by each requested domain (its ingest result, or
        ``{"error": str}`` when that domain raised), plus a ``"window"`` key
        mapping each requested domain to its resolved ``{"start", "end"}``.
    """
    resolved_path = str(get_db_path(db_path))
    resolved_end = end_date if end_date is not None else date.today().isoformat()
    requested = list(domains) if domains is not None else list(DEFAULT_DOMAINS)

    reader = GarminDBReader(db_path=resolved_path)

    results: dict[str, Any] = {}
    window: dict[str, dict[str, str]] = {}

    for domain in requested:
        if domain not in _DOMAIN_RUNNERS:
            results[domain] = {"error": f"unknown domain: {domain}"}
            continue

        window_start, window_end = _resolve_domain_window(
            domain, start_date, resolved_end, reader
        )
        window[domain] = {"start": window_start, "end": window_end}

        try:
            results[domain] = _DOMAIN_RUNNERS[domain](
                window_start, window_end, resolved_path
            )
        except Exception as exc:  # noqa: BLE001 - isolate per-domain failures
            logger.exception("catch_up_ingest: domain %s failed", domain)
            results[domain] = {"error": str(exc)}

    results["window"] = window
    return results
