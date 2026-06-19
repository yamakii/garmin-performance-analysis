"""Shared MCP response helpers.

Tool dispatch now happens directly in ``server.py`` via the single-source
registry (``garmin_mcp.tools.ALL_DEFS_BY_NAME``); the per-domain handler classes
and the ``ToolHandler`` protocol were removed in #340. These two helpers remain
because both the registry handler functions and ``server.py`` use them.
"""

import json
from collections.abc import Callable
from typing import Any


def inject_warnings(data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Add _warnings field to response data if warnings are non-empty."""
    if warnings:
        data["_warnings"] = warnings
    return data


def format_json_response(data: Any, *, default: Callable | None = None) -> str:
    """Format data as compact JSON for MCP responses."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=default)
