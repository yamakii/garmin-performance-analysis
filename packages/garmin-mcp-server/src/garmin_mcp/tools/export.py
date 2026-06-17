"""Export domain tool definition.

The ``export`` tool has a ``format`` enum + a SQL ``query`` string that cannot be
expressed cleanly via the standard schema normalization (the enum + defaults).
It therefore uses the ``input_schema_override`` escape hatch to serve the exact
hand-written schema verbatim, guaranteeing byte-for-byte MCP parity.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py``.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef


class ExportParams(BaseModel):
    """Arguments for ``export``.

    The MCP ``inputSchema`` is provided via ``input_schema_override`` (the enum +
    defaults cannot be reproduced by the standard normalization), so this model
    only drives validation and the CLI signature.
    """

    query: str
    format: Literal["parquet", "csv"] = "parquet"
    max_rows: int = 100000


_EXPORT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "DuckDB SQL query to execute",
        },
        "format": {
            "type": "string",
            "enum": ["parquet", "csv"],
            "description": "Output format (parquet recommended for efficiency)",
            "default": "parquet",
        },
        "max_rows": {
            "type": "integer",
            "description": "Safety limit for export size (default: 100000)",
            "default": 100000,
        },
    },
    "required": ["query"],
}


def _run_export(reader: GarminDBReader, p: ExportParams) -> dict[str, Any]:
    """Create an export handle and run the query, returning the result dict."""
    from garmin_mcp.mcp_server.export_manager import get_export_manager

    try:
        export_manager = get_export_manager()
        file_path, handle, expires_at = export_manager.create_export_handle(
            export_format=p.format
        )

        query_start = time.monotonic()
        metadata = reader.export_query_result(
            query=p.query,
            output_path=file_path,
            export_format=p.format,
            max_rows=p.max_rows,
        )
        query_duration = time.monotonic() - query_start

        result: dict[str, Any] = {
            "handle": handle,
            "rows": metadata["rows"],
            "size_mb": metadata["size_mb"],
            "columns": metadata["columns"],
            "expires_at": datetime.fromtimestamp(expires_at).isoformat() + "Z",
        }

        if query_duration > 5.0:
            result["_warnings"] = [
                f"Query took {query_duration:.1f}s - consider adding filters"
            ]
        return result
    except ValueError as e:
        return {
            "error": str(e),
            "suggestion": "Refine your query with WHERE clauses, LIMIT, or aggregation functions.",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"Export failed: {str(e)}"}


EXPORT_TOOLS: list[ToolDef] = [
    ToolDef(
        name="export",
        description=(
            "Export query results to file (returns handle only, not data). Use for "
            "large datasets that need processing in Python."
        ),
        params=ExportParams,
        handler=_run_export,
        cli_group="export",
        cli_name="run",
        input_schema_override=_EXPORT_INPUT_SCHEMA,
    ),
]


EXPORT_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in EXPORT_TOOLS}
