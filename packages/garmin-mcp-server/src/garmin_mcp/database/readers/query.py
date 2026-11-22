"""Inline query reader: ad-hoc SELECTs answered in the response, plus a DB map.

``export`` writes a file and suits bulk analysis in Python. A coach checking
one thing mid-conversation ("my long runs over 25 km, with pace, HR and date")
needs the rows back directly, and needs to know which table holds them. That is
what ``query_db`` and ``get_db_catalog`` serve.

The SQL is the caller's, so it runs on a sandboxed connection (no filesystem
access, read-only attach) and is wrapped as a subquery, which turns any
statement that is not a SELECT into a syntax error.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import uuid
from decimal import Decimal
from typing import Any

import duckdb

from garmin_mcp.database.connection import get_sandboxed_read_connection
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.database.table_purposes import TABLE_PURPOSES

MAX_CELL_CHARS = 400
MAX_RESPONSE_BYTES = 60_000
EXCLUDED_TABLES = frozenset({"schema_version"})

_SUGGESTION = (
    "Check table and column names with get_db_catalog (pass table= for its "
    "columns). Only a single SELECT is accepted, without a trailing semicolon."
)


def _cell(value: Any) -> Any:
    """Make one DuckDB value JSON-safe and bounded in size."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<blob {len(bytes(value))} bytes>"
    if isinstance(value, list | tuple):
        return [_cell(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _cell(v) for k, v in value.items()}
    text = value if isinstance(value, str) else str(value)
    if len(text) > MAX_CELL_CHARS:
        return f"{text[:MAX_CELL_CHARS]}…(+{len(text) - MAX_CELL_CHARS} chars)"
    return text


class QueryReader(BaseDBReader):
    """Ad-hoc read-only queries returned inline, and the table catalog."""

    def run_inline_query(self, sql: str, max_rows: int = 50) -> dict[str, Any]:
        """Run one caller-written SELECT and return its rows.

        Args:
            sql: A single DuckDB SELECT (a trailing semicolon is tolerated).
            max_rows: Rows to return at most; ``truncated`` says more existed.

        Returns:
            ``{columns, rows, row_count, truncated, note}`` or
            ``{error, suggestion}``.
        """
        body = sql.strip().rstrip(";").strip()
        wrapped = f"SELECT * FROM ({body}) AS q LIMIT {int(max_rows) + 1}"
        try:
            with get_sandboxed_read_connection(self.db_path) as conn:
                cursor = conn.execute(wrapped)
                columns = [d[0] for d in cursor.description or []]
                raw = cursor.fetchall()
        except duckdb.Error as e:
            return {"error": str(e), "suggestion": _SUGGESTION}

        truncated = len(raw) > max_rows
        rows: list[list[Any]] = []
        size = 0
        note = None
        for record in raw[:max_rows]:
            row = [_cell(v) for v in record]
            size += len(json.dumps(row, ensure_ascii=False))
            if size > MAX_RESPONSE_BYTES:
                truncated = True
                note = (
                    f"stopped at {len(rows)} rows to stay under "
                    f"{MAX_RESPONSE_BYTES} bytes; select fewer columns or aggregate"
                )
                break
            rows.append(row)
        if truncated and note is None:
            note = f"more than {max_rows} rows; aggregate, filter or raise max_rows"
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "note": note,
        }

    def _domain_tables(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = current_database() AND table_schema = 'main' "
            "ORDER BY table_name"
        ).fetchall()
        return [name for (name,) in rows if name not in EXCLUDED_TABLES]

    def catalog(self) -> list[dict[str, Any]]:
        """Every domain table with its one-line purpose and row count."""
        with get_sandboxed_read_connection(self.db_path) as conn:
            out = []
            for table in self._domain_tables(conn):
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
                out.append(
                    {
                        "table": table,
                        "purpose": TABLE_PURPOSES.get(table, ""),
                        "row_count": int(count[0]) if count else 0,
                    }
                )
        return out

    def describe_table(self, table: str) -> dict[str, Any] | None:
        """One table's purpose and columns, or None when it is not a domain table."""
        with get_sandboxed_read_connection(self.db_path) as conn:
            if table not in self._domain_tables(conn):
                return None
            info = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
        return {
            "table": table,
            "purpose": TABLE_PURPOSES.get(table, ""),
            "columns": [{"name": r[1], "type": r[2]} for r in info],
        }
