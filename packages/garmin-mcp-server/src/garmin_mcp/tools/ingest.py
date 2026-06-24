"""Catch-up ingest orchestrator tool definition (issue #463).

Exposes a single ``catch_up_ingest`` tool that fills
running/weight/strength/wellness gaps in one call by resolving an independent
window per domain and delegating to each domain's ingest primitive. Delegates
to ``ingest.catch_up``.
"""

from __future__ import annotations

import logging
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
            "strength, wellness. Domains not listed are skipped."
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


INGEST_TOOLS: list[ToolDef] = [
    ToolDef(
        name="catch_up_ingest",
        description=(
            "Differential catch-up ingest across the running, weight, strength "
            "and wellness domains in a single call. Resolves an independent "
            "window per domain (each table advances at its own pace): end_date or "
            "today as the shared end, and per-domain start = start_date (when "
            "given) or that domain's latest stored date, or end_date - 30 days "
            "when the domain is empty. running delegates to "
            "ingest_running_activities, weight to ingest_weight_range, strength "
            "to ingest_strength_sessions, wellness to ingest_wellness_range. Pass "
            "domains to ingest a subset (default: all four). A failure in one "
            "domain is isolated (its entry carries an error) while the others "
            "complete. Returns each requested domain's result plus a window map "
            "of {domain: {start, end}}."
        ),
        params=CatchUpIngestParams,
        handler=_catch_up_ingest,
        cli_group="ingest",
        cli_name="catch-up",
    ),
]


INGEST_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in INGEST_TOOLS}
