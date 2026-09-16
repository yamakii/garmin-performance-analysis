"""Gear domain tool definitions (Issue #1209).

Kept apart from ``tools/metadata.py``: that module answers "what happened on
this activity", whereas this one answers "which shoes need replacing", which is
a question about the rotation rather than about a run.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.readers.metadata import collect_gear_roster
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetGearWearParams(BaseModel):
    """Arguments for ``get_gear_wear``."""

    include_retired: bool = Field(
        default=False,
        description="Include shoes already retired in Garmin (default: false)",
    )
    as_of: str | None = Field(
        default=None,
        description=("Reference date in YYYY-MM-DD for the age axis (default: today)"),
    )


def _get_gear_wear(reader: GarminDBReader, p: GetGearWearParams) -> dict[str, Any]:
    from garmin_mcp.database.connection import get_connection

    try:
        with get_connection(reader.db_path) as conn:
            gear = collect_gear_roster(
                conn, include_retired=p.include_retired, as_of=p.as_of
            )
    except Exception as e:  # noqa: BLE001
        logger.error(f"get_gear_wear failed: {e}", exc_info=True)
        return {"success": False, "error": str(e), "gear": []}

    return {
        "success": True,
        "gear": gear,
        "replace_recommended": [
            g["gear_label"] for g in gear if g["replace_recommended"]
        ],
    }


GEAR_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_gear_wear",
        description=(
            "Get every shoe with its lifetime mileage and whether it is due for "
            "replacement, most worn first. Wear is measured against the "
            "athlete's own per-shoe limit from Garmin (gear.json "
            "maximumMeters), not a generic mileage rule, so wear_status "
            "(ok <60% / monitor 60-80% / due_soon 80-100% / over >=100%) is "
            "null when no limit is recorded rather than assumed. A second, "
            "independent axis age_status (ok / aging >=24mo / aged >=36mo) "
            "covers midsole foam degrading on the shelf regardless of use; "
            "replace_recommended takes the stricter of the two. Shoes are "
            "identified by gear_uuid, so two generations sharing one model "
            "name keep separate mileage. Retired shoes are excluded unless "
            "include_retired is true. Returns gear (gear_label, gear_model, "
            "gear_nickname, gear_uuid, runs, km, max_km, wear_pct, "
            "wear_status, first_use_date, since_date, age_months, age_status, "
            "last_used, is_retired, replace_recommended) plus a "
            "replace_recommended list of the labels needing action."
        ),
        params=GetGearWearParams,
        handler=_get_gear_wear,
        cli_group="gear",
        cli_name="wear",
    ),
]
