"""Shared MCP response helpers.

The per-domain handler classes were removed in #340 (tool dispatch now happens
directly in ``server.py`` via ``garmin_mcp.tools.ALL_DEFS_BY_NAME``). Only the
two response helpers in ``base`` remain.
"""

from garmin_mcp.handlers.base import format_json_response, inject_warnings

__all__ = [
    "format_json_response",
    "inject_warnings",
]
