"""Read-only recovery / body-composition query wrappers (Issue #502).

Thin delegators over ``GarminDBReader`` (#499/#500/#501): the recovery-trend,
recovery-status and body-composition decomposition logic all live in the reader,
so the Web layer never re-implements RHR/HRV/body-composition computation.
"""

import datetime as _dt
from pathlib import Path
from typing import Any, cast

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector

# Run-level materiality floor for the "今週の注意点" card (#677). A run lights up
# only when its form genuinely moved as a block, not just because an easy run /
# stride produced one isolated material spike (which happens almost every run).
# A run is noteworthy when EITHER:
#   - it has >= _MIN_MATERIAL_FOR_FLAG material anomalies AND >= _MIN_HIGH_FOR_FLAG
#     high-severity anomaly (scattered-but-severe), OR
#   - its largest material-only 5-minute cluster reaches
#     _MIN_MATERIAL_CLUSTER_FOR_FLAG (a concentrated form burst, even if no single
#     spike is high-severity).
_MIN_MATERIAL_FOR_FLAG = 3
_MIN_HIGH_FOR_FLAG = 1
_MIN_MATERIAL_CLUSTER_FOR_FLAG = 3


def _reader(db_path: Any) -> GarminDBReader:
    """Build a reader bound to the request's DB path (None -> default)."""
    return GarminDBReader(db_path=str(db_path) if db_path is not None else None)


def _detector_base_path(db_path: Any) -> Path | None:
    """Derive the raw-data base dir from the request's DB path.

    The form-anomaly detector reads ``raw/activity/<id>/activity_details.json``
    relative to its ``base_path``. Production layout is
    ``<data>/database/garmin_performance.duckdb``, so the data base dir is the
    db file's grandparent. ``None`` lets the detector fall back to
    ``GARMIN_DATA_DIR``.
    """
    if db_path is None:
        return None
    return Path(str(db_path)).parent.parent


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


def get_recent_form_anomaly_flags(
    db_path: Any, weeks: int = 2, max_activities: int = 12
) -> dict[str, Any]:
    """Scan the trailing ``weeks`` of runs and roll up form-anomaly flags.

    ``detect_form_anomalies_summary`` (#329) is a per-activity summary, so this
    walks the recent activities (most-recent first), runs the detector on each,
    and surfaces only the runs that actually flagged anomalies. Each detector
    call reads that activity's raw time series, so ``max_activities`` caps the
    scan; when more candidate runs exist than the cap, ``limited`` is True and
    ``scanned`` reports how many were actually inspected (no silent truncation).

    Args:
        db_path: Request DB path (None -> default).
        weeks: Trailing window length in weeks (default 2).
        max_activities: Maximum runs to scan (default 12).

    Returns:
        ``{"weeks": int, "scanned": int, "limited": bool, "flags": [...]}``
        where each flag is ``{"activity_id": int, "activity_date": str,
        "anomalies_detected": int, "severity_high": int,
        "top_recommendation": str | None}``. ``anomalies_detected`` counts only
        *material* anomalies — those with an identifiable cause (elevation /
        pace / fatigue). Runs whose anomalies are all isolated noise (no
        identifiable cause), have zero anomalies, or no usable raw data are
        omitted from ``flags`` so the card stops surfacing every run (#666).
        A run-level materiality floor (#677) further requires either a
        scattered-but-severe profile (>= ``_MIN_MATERIAL_FOR_FLAG`` material
        anomalies with >= ``_MIN_HIGH_FOR_FLAG`` high-severity) or a material
        cluster of >= ``_MIN_MATERIAL_CLUSTER_FOR_FLAG``, so easy runs / strides
        that produce only one or two material spikes no longer flag.
    """
    since = (_dt.date.today() - _dt.timedelta(weeks=weeks)).isoformat()

    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT activity_id, activity_date FROM activities "
            "WHERE activity_date >= ? ORDER BY activity_date DESC",
            [since],
        ).fetchall()

    candidates = [(int(aid), str(adate)) for aid, adate in rows]
    limited = len(candidates) > max_activities
    selected = candidates[:max_activities]

    detector = FormAnomalyDetector(base_path=_detector_base_path(db_path))

    flags: list[dict[str, Any]] = []
    for activity_id, activity_date in selected:
        try:
            summary = detector.detect_form_anomalies_summary(activity_id)
        except (FileNotFoundError, KeyError, ValueError):
            # Missing/unusable raw data -> not a flaggable run; skip silently.
            continue
        if int(summary.get("anomalies_detected", 0)) <= 0:
            continue
        summary_dict = summary.get("summary", {})
        # Count only material anomalies (identifiable cause); isolated noise is
        # excluded so runs with no real form story drop out of the card (#666).
        material = (
            int(summary_dict.get("elevation_related", 0))
            + int(summary_dict.get("pace_related", 0))
            + int(summary_dict.get("fatigue_related", 0))
        )
        if material <= 0:
            continue
        distribution = summary_dict.get("severity_distribution", {})
        # Run-level materiality floor (#677): suppress runs whose form did not
        # move as a block. Light up only on a scattered-but-severe run (enough
        # material anomalies AND at least one high-severity) or a concentrated
        # material cluster, so easy runs / strides stop flagging every week.
        severity_high = int(distribution.get("high", 0))
        max_material_cluster = int(summary_dict.get("max_material_cluster", 0))
        noteworthy = (
            material >= _MIN_MATERIAL_FOR_FLAG and severity_high >= _MIN_HIGH_FOR_FLAG
        ) or (max_material_cluster >= _MIN_MATERIAL_CLUSTER_FOR_FLAG)
        if not noteworthy:
            continue
        recommendations = summary.get("recommendations") or []
        flags.append(
            {
                "activity_id": activity_id,
                "activity_date": activity_date,
                "anomalies_detected": material,
                "severity_high": severity_high,
                "top_recommendation": recommendations[0] if recommendations else None,
            }
        )

    return {
        "weeks": weeks,
        "scanned": len(selected),
        "limited": limited,
        "flags": flags,
    }
