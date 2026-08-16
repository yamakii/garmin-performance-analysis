"""Hiking (山行) tool definitions.

Exposes two tools for the hiking summary workflow (issue #921):

- ``ingest_hiking_sessions(start_date, end_date)``: discover hiking activities
  from the Garmin API in a date window and insert summary rows into the
  ``hiking_sessions`` table. Delegates to ``ingest.hiking_ingest``.
- ``get_hiking_sessions(start_date, end_date)``: read persisted summaries from
  the ``hiking_sessions`` table (no Garmin access). Delegates to
  ``HikingSessionsReader``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class IngestHikingSessionsParams(BaseModel):
    """Arguments for ``ingest_hiking_sessions``."""

    # Optional fields are modeled as ``str | None = None`` so the derived MCP
    # schema emits no ``default`` and omits them from ``required``.
    start_date: str | None = Field(
        default=None,
        description=(
            "Inclusive window start date (YYYY-MM-DD). When omitted, catch-up "
            "resolution is used: the latest stored hiking date, or end_date - "
            "30 days when no hiking session exists yet."
        ),
    )
    end_date: str | None = Field(
        default=None,
        description=(
            "Inclusive window end date (YYYY-MM-DD). Defaults to today when " "omitted."
        ),
    )


class GetHikingSessionsParams(BaseModel):
    """Arguments for ``get_hiking_sessions``."""

    start_date: str = Field(
        description="Inclusive window start date (YYYY-MM-DD).",
    )
    end_date: str = Field(
        description="Inclusive window end date (YYYY-MM-DD).",
    )


def _ingest_hiking_sessions(
    reader: GarminDBReader, p: IngestHikingSessionsParams
) -> Any:
    from garmin_mcp.ingest.hiking_ingest import ingest_hiking_sessions

    return ingest_hiking_sessions(
        start_date=p.start_date,
        end_date=p.end_date,
        db_path=str(reader.db_path),
    )


def _get_hiking_sessions(reader: GarminDBReader, p: GetHikingSessionsParams) -> Any:
    return reader.get_hiking_sessions(p.start_date, p.end_date)


HIKING_TOOLS: list[ToolDef] = [
    ToolDef(
        name="ingest_hiking_sessions",
        description=(
            "Discover hiking (山行) activities from the Garmin Connect API in a "
            "date window and insert summary rows into the hiking_sessions "
            "table. Catch-up aware: omit start_date to ingest from the latest "
            "stored hiking date, or end_date - 30 days when none exist yet; "
            "omit end_date to default to today. Discovery uses the activity "
            "list filtered to typeKey == 'hiking'; hikes are kept out of the "
            "run-centric activities table so they never distort ACWR, load "
            "trend or form baselines. Sessions already stored are skipped. "
            "Returns discovered, ingested, skipped_existing, activity_ids, and "
            "the resolved window {start, end}."
        ),
        params=IngestHikingSessionsParams,
        handler=_ingest_hiking_sessions,
        cli_group="hiking",
        cli_name="ingest",
    ),
    ToolDef(
        name="get_hiking_sessions",
        description=(
            "Get persisted hiking (山行) summaries with activity_date in "
            "[start_date, end_date] from the hiking_sessions table (no Garmin "
            "access). Returns a list (activity_date ascending) of summaries "
            "with activity_id, activity_date, start_time_local, activity_name, "
            "duration_seconds (moving) / elapsed_duration_seconds, distance_km, "
            "elevation_gain_m, elevation_loss_m, avg/max heart rate and "
            "calories. Use it for load/recovery context only — do not apply run "
            "pace or form interpretation. Returns an empty list when none match."
        ),
        params=GetHikingSessionsParams,
        handler=_get_hiking_sessions,
        cli_group="hiking",
        cli_name="list",
    ),
]


HIKING_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in HIKING_TOOLS}
