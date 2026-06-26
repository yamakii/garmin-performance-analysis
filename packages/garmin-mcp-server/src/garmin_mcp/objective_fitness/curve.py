"""Rolling trailing-window max performance-VDOT fitness curve (pure logic).

Given a per-run performance-VDOT series (one or more points per run day), derive
an objective, non-optimistic fitness curve by taking, for each run day, the
maximum VDOT observed within the trailing ``window_days`` (boundary inclusive).

A single best-effort run is noisy; the trailing-window max smooths that noise
into a benchmark series that can be placed side-by-side with Garmin VO2max.

This module is pure: no DB, no IO, no clock access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class FitnessPoint:
    """A single point on the objective fitness curve.

    Attributes:
        date: Run day in ``YYYY-MM-DD`` format.
        vdot: Maximum performance VDOT within the trailing ``window_days``.
        source_distance_km: Distance bucket (e.g. 2.0/5.0/10.0) that produced
            the maximum VDOT.
    """

    date: str
    vdot: float
    source_distance_km: float


def rolling_max_curve(
    per_run_vdot: list[tuple[str, float, float]],
    window_days: int = 90,
) -> list[FitnessPoint]:
    """Return the trailing-window max VDOT for each run day (ascending by date).

    Args:
        per_run_vdot: Sequence of ``(date "YYYY-MM-DD", vdot, source_distance_km)``
            tuples. May be unsorted; multiple points may share a date. This is
            typically built from applying #558's ``run_best_efforts`` across all
            runs (each run's best bucket as one point, or every bucket as a point).
        window_days: Size of the trailing window in days. The window is inclusive
            of points exactly ``window_days`` before the current run day.

    Returns:
        One :class:`FitnessPoint` per distinct run day, ascending by date. For
        each day, ``vdot`` is the maximum VDOT among all input points whose date
        lies within ``[day - window_days, day]``, and ``source_distance_km`` is
        the bucket that produced that maximum. Empty input yields an empty list.
    """
    if not per_run_vdot:
        return []

    # Parse once and sort ascending by date for deterministic boundary handling.
    parsed: list[tuple[date, float, float]] = sorted(
        (
            (date.fromisoformat(d), float(vdot), float(source_distance_km))
            for d, vdot, source_distance_km in per_run_vdot
        ),
        key=lambda item: item[0],
    )

    # Distinct run days, ascending.
    run_days: list[date] = []
    for day, _vdot, _dist in parsed:
        if not run_days or run_days[-1] != day:
            run_days.append(day)

    window = timedelta(days=window_days)
    curve: list[FitnessPoint] = []
    for day in run_days:
        window_start = day - window
        best_vdot: float | None = None
        best_dist: float | None = None
        for point_day, vdot, dist in parsed:
            if point_day > day:
                break  # parsed is sorted; remaining points are in the future.
            if point_day < window_start:
                continue  # older than the trailing window.
            if best_vdot is None or vdot > best_vdot:
                best_vdot = vdot
                best_dist = dist
        # A run day always contains its own point, so best_vdot is never None.
        assert best_vdot is not None and best_dist is not None
        curve.append(
            FitnessPoint(
                date=day.isoformat(),
                vdot=best_vdot,
                source_distance_km=best_dist,
            )
        )

    return curve
