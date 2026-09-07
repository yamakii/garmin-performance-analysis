"""Catch-up ingest orchestrator tool definitions (issues #463, #1025).

Exposes ``catch_up_ingest``, which fills running/weight/strength/hiking/wellness
gaps in one call by resolving an independent window per domain and delegating to
each domain's ingest primitive, plus the read-only ``get_pending_trend_period``,
which answers "which completed week still lacks a trend narration?" independently
of any ingest run. Both delegate to ``ingest.catch_up``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class CatchUpIngestParams(BaseModel):
    """Arguments for ``catch_up_ingest``."""

    # Optional fields are modeled as ``str | None = None`` / ``list | None`` so
    # the derived MCP schema emits no ``default`` and omits them from
    # ``required``.
    start_date: str | None = Field(
        default=None,
        description=(
            "Inclusive shared window start date (YYYY-MM-DD). When omitted, each "
            "domain resolves its own start from its latest stored date (or "
            "end_date - 30 days when that domain is empty)."
        ),
    )
    end_date: str | None = Field(
        default=None,
        description=(
            "Inclusive window end date (YYYY-MM-DD). Defaults to today when " "omitted."
        ),
    )
    domains: list[str] | None = Field(
        default=None,
        description=(
            "Subset of domains to ingest. Defaults to all of running, weight, "
            "strength, hiking, wellness. Domains not listed are skipped."
        ),
    )


def _catch_up_ingest(reader: GarminDBReader, p: CatchUpIngestParams) -> Any:
    from garmin_mcp.ingest.catch_up import catch_up_ingest

    return catch_up_ingest(
        start_date=p.start_date,
        end_date=p.end_date,
        domains=p.domains,
        db_path=str(reader.db_path),
    )


class PendingTrendPeriodParams(BaseModel):
    """Arguments for ``get_pending_trend_period``."""

    end_date: str | None = Field(
        default=None,
        description=(
            "Reference date (YYYY-MM-DD) whose completed weeks are scanned. "
            "Defaults to today when omitted."
        ),
    )
    lookback_weeks: int | None = Field(
        default=None,
        description=(
            "How many completed weeks to scan, oldest first. Defaults to 4; "
            "pass 1 to look only at the week that just ended."
        ),
    )


def _get_pending_trend_period(
    reader: GarminDBReader, p: PendingTrendPeriodParams
) -> Any:
    from garmin_mcp.ingest.catch_up import find_pending_trend_period

    today = date.fromisoformat(p.end_date) if p.end_date else date.today()
    kwargs: dict[str, Any] = {}
    if p.lookback_weeks is not None:
        kwargs["lookback_weeks"] = p.lookback_weeks
    return find_pending_trend_period(str(reader.db_path), today, **kwargs)


INGEST_TOOLS: list[ToolDef] = [
    ToolDef(
        name="catch_up_ingest",
        description=(
            "Differential catch-up ingest across the running, weight, strength, "
            "hiking and wellness domains in a single call. Resolves an independent "
            "window per domain (each table advances at its own pace): end_date or "
            "today as the shared end, and per-domain start = start_date (when "
            "given) or that domain's latest stored date, or end_date - 30 days "
            "when the domain is empty. running delegates to "
            "ingest_running_activities, weight to ingest_weight_range, strength "
            "to ingest_strength_sessions, hiking to ingest_hiking_sessions, "
            "wellness to ingest_wellness_range. Pass "
            "domains to ingest a subset (default: all five). A failure in one "
            "domain is isolated (its entry carries an error) while the others "
            "complete. Returns each requested domain's result plus a window map "
            "of {domain: {start, end}}. When the running domain succeeds, the "
            "prescribed sessions in its window are also reconciled against the "
            "ingested runs and the counts are returned as "
            "prescriptions_reconciled (null when that step failed). On a "
            "fully-successful run (no domain "
            "error), if any of the last 4 completed weeks still lacks a trend "
            "narration, the result also carries trend_pending: {granularity, "
            "period_start, period_end} for the oldest such week so callers can "
            "fire trend-narration for it (idempotent: omitted once every "
            "scanned week is narrated). Use get_pending_trend_period to ask the "
            "same question without running an ingest."
        ),
        params=CatchUpIngestParams,
        handler=_catch_up_ingest,
        cli_group="ingest",
        cli_name="catch-up",
    ),
    ToolDef(
        name="get_pending_trend_period",
        description=(
            "Read-only check for a completed week that still lacks a longitudinal "
            "trend narration (trend_analyses row). Scans the lookback_weeks "
            "(default 4) most-recently-completed weeks relative to end_date "
            "(default today), oldest first, using the athlete's configured "
            "week-start day, and returns {granularity, period_start, period_end} "
            "for the first week with no narration, or null when all of them are "
            "narrated. Unlike catch_up_ingest's trend_pending field, this runs no "
            "ingest and is not gated on ingest success, so a caller (e.g. the "
            "weekly-review skill) can trigger trend-narration for the returned "
            "period even in a session that did not run catch-up."
        ),
        params=PendingTrendPeriodParams,
        handler=_get_pending_trend_period,
        cli_group="ingest",
        cli_name="pending-trend",
    ),
]


INGEST_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in INGEST_TOOLS}
