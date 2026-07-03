"""Best contiguous effort segment extraction + performance VDOT.

Pure functions (no DB/IO) shared by readers and the web app. Given a run's
ordered per-split data, slide a contiguous window to find the fastest stretch
covering a nominal distance bucket (2/5/10km), then compute the Daniels
performance VDOT for that effort via :class:`VDOTCalculator`.

The all-run average VDOT is noisy because warmups, cooldowns and easy running
drag it down; the rolling best contiguous segment per run is a cleaner fitness
signal (Epic #526 spike).
"""

from __future__ import annotations

from dataclasses import dataclass

from garmin_mcp.fitness.vdot import VDOTCalculator


@dataclass(frozen=True)
class BestEffort:
    """Fastest contiguous effort covering a nominal distance bucket.

    Attributes:
        target_distance_km: Nominal bucket (2.0 / 5.0 / 10.0).
        actual_distance_km: Summed split distance of the chosen window
            (>= target_distance_km).
        duration_seconds: Total duration of the window.
        pace_seconds_per_km: Window pace (duration / actual distance).
        vdot: Daniels performance VDOT for the window effort.
    """

    target_distance_km: float
    actual_distance_km: float
    duration_seconds: float
    pace_seconds_per_km: float
    vdot: float


def performance_vdot(distance_km: float, duration_seconds: float) -> float:
    """Daniels performance VDOT; delegates to VDOTCalculator.vdot_from_race.

    Args:
        distance_km: Effort distance in kilometers.
        duration_seconds: Effort duration in seconds.

    Returns:
        VDOT value.
    """
    return VDOTCalculator.vdot_from_race(distance_km, int(round(duration_seconds)))


def best_contiguous_segment(
    splits: list[dict],
    target_distance_km: float,
) -> BestEffort | None:
    """Slide a contiguous window over ordered splits; return the fastest window
    whose summed distance >= target_distance_km. None if the run is too short.

    For each starting split the window is grown only until its summed distance
    first reaches ``target_distance_km`` (minimal window per start), then the
    fastest such window across all starts is selected.

    Args:
        splits: Per-split dicts with ``distance`` (meters) and
            ``duration_seconds`` (seconds). Ordered by ``split_index``.
        target_distance_km: Nominal distance bucket to cover, in kilometers.

    Returns:
        The fastest qualifying ``BestEffort``, or None if no contiguous window
        reaches ``target_distance_km``.
    """
    ordered = sorted(splits, key=lambda s: s.get("split_index", 0))
    target_m = target_distance_km * 1000.0

    best: BestEffort | None = None
    n = len(ordered)
    for start in range(n):
        dist_m = 0.0
        duration = 0.0
        for end in range(start, n):
            dist_m += ordered[end]["distance"]
            duration += ordered[end]["duration_seconds"]
            if dist_m >= target_m:
                actual_km = dist_m / 1000.0
                pace = duration / actual_km
                if best is None or pace < best.pace_seconds_per_km:
                    best = BestEffort(
                        target_distance_km=target_distance_km,
                        actual_distance_km=actual_km,
                        duration_seconds=duration,
                        pace_seconds_per_km=pace,
                        vdot=performance_vdot(actual_km, duration),
                    )
                break

    return best


def run_best_efforts(
    splits: list[dict],
    buckets_km: tuple[float, ...] = (2.0, 5.0, 10.0),
) -> list[BestEffort]:
    """BestEffort (incl. performance VDOT) for each bucket the run can cover.

    Args:
        splits: Per-split dicts (see :func:`best_contiguous_segment`).
        buckets_km: Nominal distance buckets to extract.

    Returns:
        A list of ``BestEffort`` (one per coverable bucket). Buckets the run is
        too short to cover are omitted.
    """
    efforts: list[BestEffort] = []
    for bucket in buckets_km:
        effort = best_contiguous_segment(splits, bucket)
        if effort is not None:
            efforts.append(effort)
    return efforts
