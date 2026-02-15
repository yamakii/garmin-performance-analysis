"""Handler for export tool."""

import json
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader


class ExportHandler:
    """Handles export-related tool calls."""

    _tool_names: set[str] = {"export"}

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name != "export":
            raise ValueError(f"Unknown tool: {name}")

        from datetime import datetime

        from garmin_mcp.mcp_server.export_manager import get_export_manager

        query = arguments["query"]
        export_format = arguments.get("format", "parquet")
        max_rows = arguments.get("max_rows", 100000)

        try:
            # Get export manager
            export_manager = get_export_manager()

            # Create export handle
            file_path, handle, expires_at = export_manager.create_export_handle(
                export_format=export_format
            )

            # Export query result
            metadata = self._db_reader.export_query_result(
                query=query,
                output_path=file_path,
                export_format=export_format,
                max_rows=max_rows,
            )

            # Build result
            result: dict[str, Any] = {
                "handle": handle,
                "rows": metadata["rows"],
                "size_mb": metadata["size_mb"],
                "columns": metadata["columns"],
                "expires_at": datetime.fromtimestamp(expires_at).isoformat() + "Z",
            }

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        except ValueError as e:
            # Size limit exceeded
            result = {
                "error": str(e),
                "suggestion": "Refine your query with WHERE clauses, LIMIT, or aggregation functions.",
            }
            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]
        except Exception as e:
            # Other errors
            result = {"error": f"Export failed: {str(e)}"}
            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]
