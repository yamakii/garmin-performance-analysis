"""Single-source-of-truth tool registry.

Tool definitions (MCP inputSchema, dispatch, CLI subcommands) are derived from a
single ``ToolDef`` declaration per tool. See ``registry`` for the core types and
the per-domain modules (``physiology``, ``splits``, ...) for the declarations.

``ALL_DEFS`` aggregates every handler-domain tool in the exact order the legacy
``tool_schemas.get_tool_definitions()`` served them, so the live MCP surface
stays byte-for-byte identical. The two server-level tools (``get_server_info``,
``reload_server``) are intentionally *not* part of the registry: they are handled
directly in ``server.py`` and appended to the MCP tool list afterwards.
"""

from __future__ import annotations

from garmin_mcp.tools.analysis import ANALYSIS_TOOLS
from garmin_mcp.tools.athlete import ATHLETE_TOOLS
from garmin_mcp.tools.durability import DURABILITY_TOOLS
from garmin_mcp.tools.export import EXPORT_TOOLS
from garmin_mcp.tools.metadata import METADATA_TOOLS
from garmin_mcp.tools.performance import PERFORMANCE_TOOLS
from garmin_mcp.tools.physiology import PHYSIOLOGY_TOOLS
from garmin_mcp.tools.race import RACE_TOOLS
from garmin_mcp.tools.registry import ToolDef
from garmin_mcp.tools.splits import SPLITS_TOOLS
from garmin_mcp.tools.strength import STRENGTH_TOOLS
from garmin_mcp.tools.time_series import TIME_SERIES_TOOLS
from garmin_mcp.tools.training_load import LOAD_TOOLS
from garmin_mcp.tools.training_plan import TRAINING_PLAN_TOOLS

# Order mirrors the legacy get_tool_definitions() concatenation, with later
# additions (race, load, then durability) appended last; the golden snapshot is
# regenerated to match.
ALL_DEFS: list[ToolDef] = (
    EXPORT_TOOLS
    + METADATA_TOOLS
    + SPLITS_TOOLS
    + ANALYSIS_TOOLS
    + PHYSIOLOGY_TOOLS
    + PERFORMANCE_TOOLS
    + TIME_SERIES_TOOLS
    + TRAINING_PLAN_TOOLS
    + ATHLETE_TOOLS
    + RACE_TOOLS
    + LOAD_TOOLS
    + DURABILITY_TOOLS
    + STRENGTH_TOOLS
)

ALL_DEFS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ALL_DEFS}
