"""Flag splits whose pod dynamics collapsed (issue #1635).

A running-dynamics pod sometimes drops into a degraded mode (phone
interference, a loose mount): at the same pace and cadence GCT reads 30-50 ms
short and vertical oscillation 2-5 cm large. Those splits are artifacts, not
form, so they are flagged ``splits.dynamics_suspect`` at ingest and the form
paths (``split_filter.form_split_sql``) drop them. The data is kept.

Only sensors whose dynamics are *measured* (the pod) are scored; wrist
dynamics are derived from cadence and pace and are never flagged.

A split is scored against the robust spread of every *prior* split of the same
sensor in its pace bin (``PACE_BIN_S`` wide)::

    S = max(-z_gct, 0) + max(z_vo, 0)

with ``z = (x - median) / (1.4826 * MAD)``. Only the collapse directions count,
and the two axes add (an AND rule misses runs that collapse on one axis only).
``S >= SUSPECT_SCORE`` flags the split. A bin with fewer than
``MIN_BIN_SAMPLES`` reference splits is not scored.

A split whose cadence is itself clearly low (``z_cadence <= CADENCE_EXPLAINS_Z``)
is never flagged: a lower cadence physically raises VO, so that split shows a
real change in the running (a tired, bouncing stride), not a sensor artifact.
The pod collapses this module targets keep a normal cadence (z -1.3...+0.8 on
the 2026 runs), while the 2021 low-cadence bounces sat at z -2.5...-4.3.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from .split_filter import MAX_RUNNING_PACE_S_PER_KM, MIN_SPLIT_KM

logger = logging.getLogger(__name__)

PACE_BIN_S: float = 30.0
MIN_BIN_SAMPLES: int = 30
SUSPECT_SCORE: float = 5.0

#: At or below this cadence z the split's VO is explained by its low cadence.
CADENCE_EXPLAINS_Z: float = -2.0

#: Lower pace bound of the reference / scored splits (s/km); the upper bound is
#: the running-pace ceiling shared with the form filter.
MIN_REFERENCE_PACE_S_PER_KM: float = 300.0

#: Scale turning a MAD into a standard-deviation equivalent for normal data.
_MAD_SCALE = 1.4826

#: Sensors whose dynamics are measured, hence scored.
_MEASURED_SENSORS = ("pod",)


@dataclass(frozen=True)
class BinReference:
    """Robust centre and spread of GCT (ms), VO (cm) and cadence in one pace bin.

    The cadence pair is ``None`` when the bin has no usable cadence spread; the
    low-cadence guard is then skipped.
    """

    gct_median: float
    gct_mad: float
    vo_median: float
    vo_mad: float
    cadence_median: float | None = None
    cadence_mad: float | None = None


def cadence_explains(cadence: float | None, ref: BinReference) -> bool:
    """Whether the split's cadence is low enough to explain a high VO."""
    if cadence is None or ref.cadence_median is None or not ref.cadence_mad:
        return False
    return (cadence - ref.cadence_median) / ref.cadence_mad <= CADENCE_EXPLAINS_Z


def suspect_score(gct_ms: float, vo_cm: float, ref: BinReference) -> float:
    """Return the collapse score S of a split against its bin reference.

    Only a shorter-than-usual GCT and a larger-than-usual VO add to the score.
    """
    gct_z = (gct_ms - ref.gct_median) / ref.gct_mad
    vo_z = (vo_cm - ref.vo_median) / ref.vo_mad
    return max(-gct_z, 0.0) + max(vo_z, 0.0)


def _bin_of(pace_s_per_km: float) -> int:
    return math.floor(pace_s_per_km / PACE_BIN_S)


def _robust(values: np.ndarray) -> tuple[float, float]:
    median = float(np.median(values))
    return median, float(np.median(np.abs(values - median)) * _MAD_SCALE)


def _build_references(rows: list[tuple[Any, ...]]) -> dict[int, BinReference]:
    """Per pace bin references from ``(pace, gct, vo, cadence)`` rows.

    Thin bins and bins without a GCT / VO spread are skipped. Cadence may be
    NULL; its median / MAD come from the non-null values and are left ``None``
    when there are none or they have no spread.
    """
    grouped: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for pace, gct, vo, cadence in rows:
        grouped[_bin_of(float(pace))].append(
            (float(gct), float(vo), math.nan if cadence is None else float(cadence))
        )
    references: dict[int, BinReference] = {}
    for bin_id, samples in grouped.items():
        if len(samples) < MIN_BIN_SAMPLES:
            continue
        array = np.asarray(samples, dtype=float)
        gct_median, gct_mad = _robust(array[:, 0])
        vo_median, vo_mad = _robust(array[:, 1])
        if gct_mad <= 0 or vo_mad <= 0:
            continue
        cadences = array[:, 2][~np.isnan(array[:, 2])]
        cadence_median: float | None = None
        cadence_mad: float | None = None
        if cadences.size:
            cadence_median, cadence_mad = _robust(cadences)
            if cadence_mad <= 0:
                cadence_median, cadence_mad = None, None
        references[bin_id] = BinReference(
            gct_median, gct_mad, vo_median, vo_mad, cadence_median, cadence_mad
        )
    return references


def flag_suspect_dynamics(conn: Any, activity_id: int) -> int:
    """Set ``splits.dynamics_suspect`` for one activity; return the flag count.

    Rewrites the activity's flags from scratch, so re-running is idempotent.
    Activities whose dynamics are not measured (wrist / unknown) are left
    FALSE. The reference is every split of the same sensor from activities that
    precede this one (earlier date, or same date and lower id).
    """
    head = conn.execute(
        "SELECT activity_date, dynamics_source FROM activities WHERE activity_id = ?",
        [activity_id],
    ).fetchone()
    conn.execute(
        "UPDATE splits SET dynamics_suspect = FALSE WHERE activity_id = ?",
        [activity_id],
    )
    if head is None or head[1] not in _MEASURED_SENSORS:
        return 0
    activity_date, sensor = head

    base_where = (
        "s.distance >= ? AND s.pace_seconds_per_km >= ? AND s.pace_seconds_per_km < ? "
        "AND s.ground_contact_time IS NOT NULL "
        "AND s.vertical_oscillation IS NOT NULL"
    )
    base_params = [
        MIN_SPLIT_KM,
        MIN_REFERENCE_PACE_S_PER_KM,
        MAX_RUNNING_PACE_S_PER_KM,
    ]
    reference_rows = conn.execute(
        f"""
        SELECT s.pace_seconds_per_km, s.ground_contact_time, s.vertical_oscillation,
               s.cadence
        FROM splits s JOIN activities a ON a.activity_id = s.activity_id
        WHERE a.dynamics_source = ?
          AND (a.activity_date < ?
               OR (a.activity_date = ? AND a.activity_id < ?))
          AND {base_where}
        """,
        [sensor, activity_date, activity_date, activity_id, *base_params],
    ).fetchall()
    references = _build_references(reference_rows)
    if not references:
        return 0

    own_rows = conn.execute(
        f"""
        SELECT s.split_index, s.pace_seconds_per_km, s.ground_contact_time,
               s.vertical_oscillation, s.cadence
        FROM splits s
        WHERE s.activity_id = ? AND {base_where}
        """,
        [activity_id, *base_params],
    ).fetchall()
    flagged = []
    for split_index, pace, gct, vo, cadence in own_rows:
        ref = references.get(_bin_of(float(pace)))
        if ref is None:
            continue
        if suspect_score(float(gct), float(vo), ref) < SUSPECT_SCORE:
            continue
        if cadence_explains(None if cadence is None else float(cadence), ref):
            continue
        flagged.append(split_index)
    for split_index in flagged:
        conn.execute(
            "UPDATE splits SET dynamics_suspect = TRUE "
            "WHERE activity_id = ? AND split_index = ?",
            [activity_id, split_index],
        )
    if flagged:
        logger.info(
            "Flagged %d suspect pod-dynamics splits for activity %s",
            len(flagged),
            activity_id,
        )
    return len(flagged)
