"""Read-only single-run report query wrapper (#1250).

A thin delegator over ``GarminDBReader.get_run_report``: the whole report is
assembled in the reader (the Web package must never import ``garmin_mcp.rag``,
and the heat-adjustment model behind the HR signal lives there), so this layer
only forwards the call on the request's connection.
"""

from typing import Any, cast

import duckdb
from garmin_mcp.database.db_reader import GarminDBReader


def get_run_report(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> dict[str, Any] | None:
    """The deterministic run report for ``activity_id`` (``None`` if unknown)."""
    return cast(
        "dict[str, Any] | None",
        GarminDBReader.from_connection(conn).get_run_report(activity_id),
    )
