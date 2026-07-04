"""Read-only recovery / body-composition query wrappers (Issue #502).

Thin delegators over ``GarminDBReader`` (#499/#500/#501): the recovery-trend,
recovery-status and body-composition decomposition logic all live in the reader,
so the Web layer never re-implements RHR/HRV/body-composition computation.
"""

from typing import Any, cast

import duckdb
from garmin_mcp.database.db_reader import GarminDBReader


def get_recovery_trend(
    conn: duckdb.DuckDBPyConnection, weeks: int = 8
) -> dict[str, Any]:
    """RHR / HRV recovery trend over the trailing ``weeks`` (delegates to #499)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_recovery_trend(weeks),
    )


def get_recovery_status(
    conn: duckdb.DuckDBPyConnection, date: str | None = None
) -> dict[str, Any]:
    """Morning go/no-go recovery status for ``date`` (delegates to #500)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_recovery_status(date),
    )


def get_body_composition_trend(
    conn: duckdb.DuckDBPyConnection, weeks: int = 12
) -> dict[str, Any]:
    """Body-composition trend over the trailing ``weeks`` (delegates to #501)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_body_composition_trend(weeks),
    )


def get_weight_economy_coupling(
    conn: duckdb.DuckDBPyConnection, weeks: int = 52
) -> dict[str, Any]:
    """Weight-economy coupling over the trailing ``weeks`` (delegates to #554)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_weight_economy_coupling(weeks=weeks),
    )


def get_wellness_baseline_deviation(
    conn: duckdb.DuckDBPyConnection, date: str | None = None, window_days: int = 30
) -> dict[str, Any]:
    """Personal-baseline deviation for HRV / readiness / RHR (delegates to #555)."""
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_wellness_baseline_deviation(
            date, window_days
        ),
    )


def get_recent_form_anomaly_flags(
    conn: duckdb.DuckDBPyConnection, weeks: int = 2, max_activities: int = 12
) -> dict[str, Any]:
    """Roll up recent runs whose form flagged material anomalies (delegates #809).

    The material-event aggregation and the personal-baseline flag rule live in
    ``GarminDBReader.get_recent_form_anomaly_flags`` -- the single source shared
    with the injury-risk signal -- so the Web layer never re-implements the
    detector scan. See the reader for the response schema and flag semantics.
    """
    return cast(
        "dict[str, Any]",
        GarminDBReader.from_connection(conn).get_recent_form_anomaly_flags(
            weeks, max_activities
        ),
    )
