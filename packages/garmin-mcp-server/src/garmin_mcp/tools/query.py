"""Inline query domain tool definitions (#1604).

``query_db`` answers a caller-written SELECT in the response, so a session can
check something in the athlete's history mid-conversation without the
export-to-file round trip. ``get_db_catalog`` says which table answers what.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef


class QueryDbParams(BaseModel):
    """Arguments for ``query_db``."""

    sql: str = Field(
        description=(
            "One DuckDB SELECT (WITH ... SELECT is fine). It runs wrapped as a "
            "subquery, so no other statement type and no trailing semicolon"
        )
    )
    max_rows: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Rows to return at most, 1-200 (default 50)",
    )


class GetDbCatalogParams(BaseModel):
    """Arguments for ``get_db_catalog``."""

    table: str | None = Field(
        default=None,
        description="A table name for its columns; omit for every table",
    )


def _query_db(reader: GarminDBReader, p: QueryDbParams) -> Any:
    return reader.run_inline_query(p.sql, p.max_rows)


def _get_db_catalog(reader: GarminDBReader, p: GetDbCatalogParams) -> Any:
    return reader.db_catalog(p.table)


QUERY_TOOLS: list[ToolDef] = [
    ToolDef(
        name="query_db",
        description=(
            "Run one read-only SELECT against the athlete's DuckDB and get the "
            "rows back in the response: for checking the athlete's own history "
            "mid-conversation (comparable past runs, a metric over months, what "
            "a block or review said). Returns columns, rows (lists in column "
            "order), row_count, truncated (more rows existed than returned) and "
            "note, or error with a suggestion. Dates come back as ISO strings; "
            "text cells over 400 chars are cut. No file access. Find tables and "
            "columns with get_db_catalog; use export for bulk analysis in Python."
        ),
        params=QueryDbParams,
        handler=_query_db,
        cli_group="query",
        cli_name="run",
    ),
    ToolDef(
        name="get_db_catalog",
        description=(
            "Map of the athlete's DuckDB. Without table: every domain table with "
            "a one-line purpose (what it answers, its grain) and row_count, as "
            "tables. With table: its purpose and columns [{name, type}], or "
            "error for an unknown table. Use it to find where a question's data "
            "lives before writing a query_db SELECT."
        ),
        params=GetDbCatalogParams,
        handler=_get_db_catalog,
        cli_group="query",
        cli_name="catalog",
    ),
]
