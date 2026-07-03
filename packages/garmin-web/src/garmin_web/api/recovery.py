"""Recovery / body-composition API router (read-only, Issue #502).

Wraps ``GarminDBReader`` (#499/#500/#501) via ``queries.recovery``: all RHR/HRV
recovery and body-composition decomposition logic lives in the reader, so the
Web layer stays a thin pass-through.
"""

from typing import Any

from fastapi import APIRouter, Request
from garmin_mcp.database.connection import get_connection

from garmin_web.queries import recovery as recovery_queries

router = APIRouter(prefix="/api")


def _db_path(request: Request) -> Any:
    return getattr(request.app.state, "db_path", None)


@router.get("/recovery-trend")
def get_recovery_trend_endpoint(request: Request, weeks: int = 8) -> dict[str, Any]:
    """RHR / HRV recovery trend over the trailing ``weeks`` weeks (#499).

    Read-only: delegates entirely to the reader. ``series`` is date-ascending;
    ``rhr`` / ``hrv`` summary fields are null-safe when data is missing.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_recovery_trend(conn, weeks)


@router.get("/recovery-status")
def get_recovery_status_endpoint(
    request: Request, date: str | None = None
) -> dict[str, Any]:
    """Morning go/no-go recovery status for ``date`` (#500).

    ``date`` defaults to the latest day in ``daily_wellness``. A device-off day
    returns ``recommendation="unknown"`` with a "go by feel" reason.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_recovery_status(conn, date)


@router.get("/body-composition-trend")
def get_body_composition_trend_endpoint(
    request: Request, weeks: int = 12
) -> dict[str, Any]:
    """Body-composition trend over the trailing ``weeks`` weeks (#501).

    Read-only: ``series`` is date-ascending with fat/lean decomposition, and
    ``change`` carries the first-to-last weight delta breakdown.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_body_composition_trend(conn, weeks)


@router.get("/form-anomaly-flags")
def get_form_anomaly_flags_endpoint(
    request: Request, weeks: int = 2, max_activities: int = 12
) -> dict[str, Any]:
    """ "今週の注意点": form-anomaly flags across the trailing ``weeks`` runs (#636).

    Rolls up the per-activity ``detect_form_anomalies_summary`` over recent runs.
    ``max_activities`` caps the scan; ``limited`` is True when more candidate
    runs existed than were scanned (``scanned``). Never 500s on missing raw data.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_recent_form_anomaly_flags(
            conn, weeks, max_activities
        )


@router.get("/weight-economy-coupling")
def get_weight_economy_coupling_endpoint(
    request: Request, weeks: int = 52
) -> dict[str, Any]:
    """Weight <-> easy-run economy (EF) coupling over the trailing ``weeks`` (#554).

    Read-only: delegates entirely to the reader. ``series`` overlays each easy
    run's EF on its nearest body-weight measurement; ``model`` carries the
    longitudinal effect size + collinearity (association) caveat, or ``None``
    when too few runs matched. Never 500s on insufficient data.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_weight_economy_coupling(conn, weeks)


@router.get("/wellness-baseline-deviation")
def get_wellness_baseline_deviation_endpoint(
    request: Request, date: str | None = None, window_days: int = 30
) -> dict[str, Any]:
    """Personal-baseline deviation for HRV / readiness / RHR on ``date`` (#555).

    Read-only: delegates entirely to the reader. Builds a rolling personal band
    (mean +/- SD over the trailing ``window_days``) for each metric and judges
    the target day against its own band as a z-score. ``date`` defaults to the
    latest day in ``daily_wellness``; bands with fewer than 7 samples are
    ``flag="insufficient"`` (null-safe, never 500s). ``overall_flag`` is True
    when any metric sits in an unfavorable deviation.
    """
    with get_connection(_db_path(request)) as conn:
        return recovery_queries.get_wellness_baseline_deviation(conn, date, window_days)
