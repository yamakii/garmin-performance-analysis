"""Read-only per-split form-anomaly query wrapper (Issue #1132).

A thin delegator over ``GarminDBReader.get_split_form_anomalies``: the detector
run and the timestamp -> split mapping both live in the reader (the Web package
must never import ``garmin_mcp.rag``), so this layer only forwards the call.
"""

from typing import Any, cast

import duckdb
from garmin_mcp.database.db_reader import GarminDBReader


def get_split_form_anomalies(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> dict[str, Any]:
    """Per-split form-anomaly counts for ``activity_id`` (delegates to #1132)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_split_form_anomalies(activity_id),
    )
