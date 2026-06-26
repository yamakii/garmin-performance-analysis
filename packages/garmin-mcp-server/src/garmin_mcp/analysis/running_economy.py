"""Running-economy weight-join helpers (pure functions, no I/O).

Couples each (easy) run with a body weight by nearest-neighbour date matching
against ``body_composition`` measurements, and derives running-economy metrics
(efficiency factor ``EF = avg_speed_ms / avg_heart_rate``). These helpers are the
analytic core behind the longitudinal weight x running-economy analysis (#525,
#552).

The functions take plain row lists (no DB handle) so they are unit-testable in
isolation; the reader is responsible for fetching ``RunRecord`` / ``WeightMeasurement``
rows and passing them in. ``activities.body_mass_kg`` is intentionally *not* used
(only 2/526 rows are back-filled); weight always comes from ``body_composition``.

All functions are null-safe: degenerate inputs (non-positive HR/speed, no weight
within the window) yield ``None`` / a dropped row rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Maximum allowed gap (days) between a run and the nearest weight measurement.
# spike (#525) showed a median join gap of 0 days; 14 days keeps n high while
# avoiding stale weights.
DEFAULT_MAX_GAP_DAYS = 14


@dataclass(frozen=True)
class RunRecord:
    """A single run to be coupled with a body weight."""

    activity_id: int
    run_date: date
    avg_speed_ms: float
    avg_heart_rate: float


@dataclass(frozen=True)
class WeightMeasurement:
    """A ``body_composition`` weight measurement."""

    measure_date: date
    weight_kg: float


@dataclass(frozen=True)
class CoupledRecord:
    """A run joined with its nearest body weight and derived EF."""

    activity_id: int
    run_date: date
    weight_kg: float
    weight_gap_days: int  # absolute day delta to the joined measurement
    ef: float  # avg_speed_ms / avg_heart_rate
    avg_heart_rate: float
    avg_speed_ms: float


def compute_ef(avg_speed_ms: float, avg_heart_rate: float) -> float | None:
    """EF = speed / HR.

    Args:
        avg_speed_ms: Average speed (m/s).
        avg_heart_rate: Average heart rate (bpm).

    Returns:
        ``avg_speed_ms / avg_heart_rate`` when both inputs are positive, else
        ``None`` (null-safe; never raises). A non-positive speed or HR makes the
        efficiency factor undefined.
    """
    if avg_heart_rate <= 0 or avg_speed_ms <= 0:
        return None
    return avg_speed_ms / avg_heart_rate


def nearest_weight(
    run_date: date,
    measurements: list[WeightMeasurement],
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
) -> tuple[float, int] | None:
    """Find the measurement closest in time to ``run_date``.

    Args:
        run_date: The run's date.
        measurements: Candidate weight measurements (any order).
        max_gap_days: Maximum allowed absolute day gap; matches outside this
            window are rejected.

    Returns:
        ``(weight_kg, gap_days)`` for the nearest measurement within
        ``max_gap_days`` (gap is the absolute day delta), or ``None`` when no
        measurement falls inside the window. On a tie the earlier (past)
        measurement is preferred.
    """
    best: tuple[float, int] | None = None
    best_signed_gap: int | None = None
    for m in measurements:
        gap = abs((run_date - m.measure_date).days)
        if gap > max_gap_days:
            continue
        # Negative signed gap = measurement is in the past (or same day). On a
        # tie in absolute gap, the smaller signed gap (past side) wins.
        signed_gap = (m.measure_date - run_date).days
        if (
            best is None
            or gap < best[1]
            or (
                best_signed_gap is not None
                and gap == best[1]
                and signed_gap < best_signed_gap
            )
        ):
            best = (m.weight_kg, gap)
            best_signed_gap = signed_gap
    return best


def join_runs_with_weight(
    runs: list[RunRecord],
    measurements: list[WeightMeasurement],
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
) -> list[CoupledRecord]:
    """Join each run with its nearest body weight and derive EF.

    Args:
        runs: Runs to couple (any order).
        measurements: Candidate weight measurements.
        max_gap_days: Maximum allowed absolute day gap for the join.

    Returns:
        One ``CoupledRecord`` per run that has a weight within ``max_gap_days``
        *and* a computable EF (positive speed and HR). Runs without a matching
        weight or with a degenerate EF are dropped. Results are sorted by
        ``run_date`` ascending.
    """
    coupled: list[CoupledRecord] = []
    for run in runs:
        match = nearest_weight(run.run_date, measurements, max_gap_days)
        if match is None:
            continue
        ef = compute_ef(run.avg_speed_ms, run.avg_heart_rate)
        if ef is None:
            continue
        weight_kg, gap_days = match
        coupled.append(
            CoupledRecord(
                activity_id=run.activity_id,
                run_date=run.run_date,
                weight_kg=weight_kg,
                weight_gap_days=gap_days,
                ef=ef,
                avg_heart_rate=run.avg_heart_rate,
                avg_speed_ms=run.avg_speed_ms,
            )
        )
    coupled.sort(key=lambda r: r.run_date)
    return coupled
