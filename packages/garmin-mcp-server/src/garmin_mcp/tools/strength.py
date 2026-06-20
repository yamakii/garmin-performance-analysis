"""Strength-training (補強) tool definitions.

Exposes two tools for the strength_training summary workflow (issue #450):

- ``ingest_strength_sessions(start_date, end_date)``: discover strength_training
  activities from the Garmin API in a date window, aggregate each session's
  ACTIVE exercise-set categories, and upsert summary rows into the
  ``strength_sessions`` table. Delegates to ``ingest.strength_ingest``.
- ``get_strength_sessions(start_date, end_date)``: read persisted summaries from
  the ``strength_sessions`` table (no Garmin access). Delegates to
  ``StrengthSessionsReader``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class IngestStrengthSessionsParams(BaseModel):
    """Arguments for ``ingest_strength_sessions``."""

    start_date: str = Field(
        description="Inclusive window start date (YYYY-MM-DD).",
    )
    end_date: str = Field(
        description="Inclusive window end date (YYYY-MM-DD).",
    )


class GetStrengthSessionsParams(BaseModel):
    """Arguments for ``get_strength_sessions``."""

    start_date: str = Field(
        description="Inclusive window start date (YYYY-MM-DD).",
    )
    end_date: str = Field(
        description="Inclusive window end date (YYYY-MM-DD).",
    )


def _ingest_strength_sessions(
    reader: GarminDBReader, p: IngestStrengthSessionsParams
) -> Any:
    from garmin_mcp.ingest.strength_ingest import ingest_strength_sessions

    return ingest_strength_sessions(
        p.start_date, p.end_date, db_path=str(reader.db_path)
    )


def _get_strength_sessions(reader: GarminDBReader, p: GetStrengthSessionsParams) -> Any:
    return reader.get_strength_sessions(p.start_date, p.end_date)


STRENGTH_TOOLS: list[ToolDef] = [
    ToolDef(
        name="ingest_strength_sessions",
        description=(
            "Discover strength_training (補強) activities from the Garmin Connect "
            "API in a date window and upsert summary rows into the "
            "strength_sessions table. Discovery uses the activity list filtered "
            "to typeKey == 'strength_training' (runs with distance are excluded). "
            "Each session's ACTIVE exercise sets are aggregated into a "
            'category_counts map (e.g. {"CRUNCH": 4, "PLANK": 7}). Idempotent: '
            "re-ingesting an activity overwrites its row. Returns inserted, "
            "updated, and activity_ids."
        ),
        params=IngestStrengthSessionsParams,
        handler=_ingest_strength_sessions,
        cli_group="strength",
        cli_name="ingest",
    ),
    ToolDef(
        name="get_strength_sessions",
        description=(
            "Get persisted strength_training (補強) summaries with activity_date "
            "in [start_date, end_date] from the strength_sessions table (no "
            "Garmin access). Returns a list (activity_date ascending) of "
            "summaries with activity_id, activity_date, start_time_local, "
            "activity_name, active/elapsed duration, avg/max heart rate, "
            "calories, active/total sets and category_counts (a dict of ACTIVE "
            "exercise-set categories). Returns an empty list when none match."
        ),
        params=GetStrengthSessionsParams,
        handler=_get_strength_sessions,
        cli_group="strength",
        cli_name="list",
    ),
]


STRENGTH_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in STRENGTH_TOOLS}
