"""Read-only recovery / body-composition query wrappers (Issue #502).

Thin delegators over ``GarminDBReader`` (#499/#500/#501): the recovery-trend,
recovery-status and body-composition decomposition logic all live in the reader,
so the Web layer never re-implements RHR/HRV/body-composition computation.
"""

from typing import Any, cast

from garmin_mcp.database.db_reader import GarminDBReader


def _reader(db_path: Any) -> GarminDBReader:
    """Build a reader bound to the request's DB path (None -> default)."""
    return GarminDBReader(db_path=str(db_path) if db_path is not None else None)


def get_recovery_trend(db_path: Any, weeks: int = 8) -> dict[str, Any]:
    """RHR / HRV recovery trend over the trailing ``weeks`` (delegates to #499)."""
    return cast("dict[str, Any]", _reader(db_path).get_recovery_trend(weeks))


def get_recovery_status(db_path: Any, date: str | None = None) -> dict[str, Any]:
    """Morning go/no-go recovery status for ``date`` (delegates to #500)."""
    return cast("dict[str, Any]", _reader(db_path).get_recovery_status(date))


def get_body_composition_trend(db_path: Any, weeks: int = 12) -> dict[str, Any]:
    """Body-composition trend over the trailing ``weeks`` (delegates to #501)."""
    return cast("dict[str, Any]", _reader(db_path).get_body_composition_trend(weeks))


def get_weight_economy_coupling(db_path: Any, weeks: int = 52) -> dict[str, Any]:
    """Weight-economy coupling over the trailing ``weeks`` (delegates to #554)."""
    return cast(
        "dict[str, Any]",
        _reader(db_path).get_weight_economy_coupling(weeks=weeks),
    )


def get_wellness_baseline_deviation(
    db_path: Any, date: str | None = None, window_days: int = 30
) -> dict[str, Any]:
    """Personal-baseline deviation for HRV / readiness / RHR (delegates to #555)."""
    return cast(
        "dict[str, Any]",
        _reader(db_path).get_wellness_baseline_deviation(date, window_days),
    )
