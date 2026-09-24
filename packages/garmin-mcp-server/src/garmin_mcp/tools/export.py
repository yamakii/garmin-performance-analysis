"""Export domain tool definition.

The ``export`` tool's MCP ``inputSchema`` is derived from ``ExportParams`` via
the registry normalizer: ``Literal[...]`` -> ``enum`` and the explicit non-None
defaults are emitted, so no ``input_schema_override`` is needed. Per-property
descriptions are supplied via ``field_descriptions`` (copied verbatim from the
previous hand-written schemas in ``tool_schemas.py``).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef


class ExportParams(BaseModel):
    """Arguments for ``export`` (drives validation, CLI, and the MCP schema)."""

    query: str = Field(
        description=(
            "A single DuckDB SELECT, wrapped as a subquery, so no trailing semicolon"
        )
    )
    format: Literal["parquet", "csv"] = Field(
        default="parquet",
        description="parquet (default) or csv with a header row",
    )
    max_rows: int = Field(
        default=100000,
        description=(
            "Refuse the export when the result has more rows than this "
            "(default: 100000)"
        ),
    )


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

        if metadata["rows"] == 0:
            # No file is written for an empty result, so there is nothing to
            # hand back or expire.
            export_manager.discard_export_handle(handle)
            result: dict[str, Any] = {
                "handle": None,
                "rows": 0,
                "size_mb": 0.0,
                "columns": metadata["columns"],
                "expires_at": None,
            }
        else:
            result = {
                "handle": handle,
                "rows": metadata["rows"],
                "size_mb": metadata["size_mb"],
                "columns": metadata["columns"],
                "expires_at": datetime.fromtimestamp(expires_at, tz=UTC).isoformat(),
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
            "Run a read-only DuckDB SELECT and write the result to a local parquet "
            "or CSV file instead of returning rows. Returns handle (the file path "
            "under /tmp/garmin_exports, deleted after 1 hour), rows, columns, "
            "size_mb and expires_at (UTC ISO 8601), or error (with a suggestion "
            "when rows exceed max_rows). Use it for multi-activity analysis read "
            "back in Python. An empty result writes no file and returns rows=0 "
            "with handle and expires_at null."
        ),
        params=ExportParams,
        handler=_run_export,
        cli_group="export",
        cli_name="run",
    ),
]


EXPORT_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in EXPORT_TOOLS}
