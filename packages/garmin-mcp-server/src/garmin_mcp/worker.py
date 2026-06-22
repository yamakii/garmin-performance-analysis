"""Fresh-process execution backend for the MCP shim.

The worker is a *pure execution backend*: it holds no MCP protocol state. It is
spawned as a short-lived ``python -m garmin_mcp.worker`` process that imports the
latest on-disk code and speaks newline-delimited JSON over stdin/stdout with the
stable shim. Because each spawn imports fresh modules, swapping the worker
process is the foundation of hot-reload: restart the worker and the new code is
live.

IPC contract (one line = one JSON object):

- request : ``{"id": int, "op": "schema"|"call"|"info", "tool": str, "args": {...}}``
- response: ``{"id": int, "ok": true, "data": ...}``
           / ``{"id": int, "ok": false, "error": str}``

``op`` semantics:

- ``schema`` -- JSON-ize ``build_mcp_tools(ALL_DEFS)`` (name/description/inputSchema
  list) for the *domain* tools only. The two server tools (``get_server_info``,
  ``reload_server``) are appended by the shim, not the worker.
- ``call``   -- ``dispatch(ALL_DEFS_BY_NAME, GarminDBReader(...), tool, args)`` and
  return a value that is ``json.dumps(..., default=str)``-serializable.
- ``info``   -- DB diagnostics (``SHOW TABLES`` count, ``MAX(start_time_local)``,
  ``started_at``).

All exceptions are caught and returned as ``{"ok": false, "error": repr(e)}`` so
the worker never crashes mid-loop. ``datetime.date`` values are made
JSON-serializable via ``default=str``.
"""

from __future__ import annotations

import json
import signal
import sys
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from garmin_mcp.database.connection import get_connection, get_db_path
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import build_mcp_tools, dispatch

# Captured at import so each fresh worker process reports its own start time.
_STARTED_AT = datetime.now(UTC).isoformat()


def build_schema() -> list[dict[str, Any]]:
    """Return the domain tools' MCP schema as plain JSON-serializable dicts.

    The two server tools (``get_server_info``, ``reload_server``) are *not*
    included; the shim appends them after receiving the worker schema.

    Returns:
        A list of ``{"name", "description", "inputSchema"}`` dicts, one per
        domain tool, in registry order.
    """
    tools = build_mcp_tools(ALL_DEFS)
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
        }
        for tool in tools
    ]


def _db_info() -> dict[str, Any]:
    """Collect best-effort DB diagnostics.

    Never raises: connection/query failures degrade to ``table_count=0`` and
    ``last_ingest_date=None`` so the response shape stays stable.
    """
    info: dict[str, Any] = {
        "db_path": str(get_db_path()),
        "started_at": _STARTED_AT,
        "table_count": 0,
        "last_ingest_date": None,
    }
    try:
        with get_connection() as conn:
            tables = conn.execute("SHOW TABLES").fetchall()
            info["table_count"] = len(tables)
            row = conn.execute(
                "SELECT MAX(start_time_local) FROM activities"
            ).fetchone()
            info["last_ingest_date"] = str(row[0]) if row and row[0] else None
    except Exception as e:  # pragma: no cover - exercised via integration/info
        info["db_error"] = repr(e)
    return info


def handle(req: dict[str, Any], reader: GarminDBReader) -> dict[str, Any]:
    """Handle a single IPC request and return a response dict.

    Args:
        req: Parsed request object (``id``/``op``/``tool``/``args``).
        reader: A reused ``GarminDBReader`` for ``call`` dispatch.

    Returns:
        A response dict with ``ok`` plus either ``data`` (success) or ``error``.
        ``id`` is echoed back when present in the request. Exceptions are caught
        and reported as ``ok=False`` so the worker loop never dies.
    """
    resp: dict[str, Any] = {}
    if "id" in req:
        resp["id"] = req["id"]

    op = req.get("op")
    try:
        if op == "schema":
            resp["ok"] = True
            resp["data"] = build_schema()
        elif op == "call":
            tool = req["tool"]
            args = req.get("args") or {}
            result = dispatch(ALL_DEFS_BY_NAME, reader, tool, args)
            # Round-trip through json to surface serialization errors here (where
            # they can be reported as ok=False) rather than in the main loop.
            resp["ok"] = True
            resp["data"] = json.loads(json.dumps(result, default=str))
        elif op == "info":
            resp["ok"] = True
            resp["data"] = _db_info()
        else:
            resp["ok"] = False
            resp["error"] = f"unknown op: {op!r}"
    except Exception as e:
        resp["ok"] = False
        resp["error"] = repr(e)
    return resp


def _install_sigterm_handler() -> None:
    """Run export/view cleanup on SIGTERM before exiting.

    Cleanup is best-effort: managers that were never initialized are skipped.
    """

    def _on_term(_signum: int, _frame: FrameType | None) -> None:
        try:
            from garmin_mcp.mcp_server.export_manager import get_export_manager

            get_export_manager().cleanup_all()
        except Exception:
            pass
        try:
            from garmin_mcp.mcp_server.view_manager import get_view_manager

            get_view_manager().cleanup_all()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_term)


def main() -> None:
    """Read stdin line-by-line, dispatch each request, write one JSON line out.

    A single ``GarminDBReader`` is created up front and reused across requests.
    Blank lines are ignored; malformed JSON is reported as ``ok=False`` rather
    than crashing the loop. SIGTERM triggers export/view cleanup then exit.
    """
    _install_sigterm_handler()
    reader = GarminDBReader(str(get_db_path()))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            resp: dict[str, Any] = {"ok": False, "error": repr(e)}
        else:
            resp = handle(req, reader)
        sys.stdout.write(json.dumps(resp, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
