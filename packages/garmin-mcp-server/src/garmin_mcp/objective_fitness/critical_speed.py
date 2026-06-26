"""Quarterly Critical Speed fit from real-run best-effort frontier.

Pure functions (no DB/IO) that fit a 2-parameter Critical Speed model to a
run's best-effort distance/duration points within the 2-45 min frontier::

    d = CS * t + D'

The slope ``CS`` (m/s) is the critical speed; the intercept ``D'`` (m) is the
classic anaerobic distance capacity. **Here D' is computed but documented
invalid**: without genuine short (<4 min) all-out anchors and long true-maximal
efforts, the intercept is meaningless and must not be surfaced as anaerobic
capacity. The fit is therefore labelled ``threshold-anchored`` and CS is
presented only as a lactate-threshold speed proxy (Epic #526 spike:
CS=2.83 m/s = 5:53/km, D'=234 m invalid, R^2=0.9998).
"""

from __future__ import annotations

from dataclasses import dataclass

# Frontier window for the 2-parameter fit (seconds): 2 min .. 45 min.
_MIN_DURATION_S = 120.0
_MAX_DURATION_S = 2700.0

_THRESHOLD_ANCHORED_LABEL = "threshold-anchored (no short/long max effort)"


@dataclass(frozen=True)
class CriticalSpeedFit:
    """Result of a 2-parameter Critical Speed fit over a best-effort frontier.

    Attributes:
        cs_mps: Slope of ``d = CS*t + D'`` = critical speed (m/s).
        cs_pace_sec_per_km: ``1000 / cs_mps`` (seconds per km).
        d_prime_m: Intercept (m). Internal value only; documented invalid and
            never surfaced as anaerobic capacity (no short/long max efforts).
        r_squared: Coefficient of determination of the linear fit.
        n_points: Number of frontier points used for the fit.
        label: Always notes the ``threshold-anchored`` caveat.
    """

    cs_mps: float
    cs_pace_sec_per_km: float
    d_prime_m: float
    r_squared: float
    n_points: int
    label: str = _THRESHOLD_ANCHORED_LABEL


def fit_critical_speed(
    efforts: list[tuple[float, float]],
) -> CriticalSpeedFit | None:
    """Fit ``d = CS*t + D'`` by 2-parameter linear least squares.

    Args:
        efforts: ``(duration_seconds, distance_m)`` best-effort points already
            restricted to the 2-45 min frontier.

    Returns:
        A :class:`CriticalSpeedFit`, or ``None`` if fewer than 2 points are
        given (slope is undefined). ``d_prime_m`` is computed but documented
        invalid and is not meant to be surfaced as anaerobic capacity.
    """
    if len(efforts) < 2:
        return None

    n = len(efforts)
    sum_t = sum(t for t, _ in efforts)
    sum_d = sum(d for _, d in efforts)
    sum_tt = sum(t * t for t, _ in efforts)
    sum_td = sum(t * d for t, d in efforts)

    denom = n * sum_tt - sum_t * sum_t
    if denom == 0:
        # All efforts share the same duration; slope is undefined.
        return None

    cs_mps = (n * sum_td - sum_t * sum_d) / denom
    d_prime_m = (sum_d - cs_mps * sum_t) / n

    mean_d = sum_d / n
    ss_tot = sum((d - mean_d) ** 2 for _, d in efforts)
    ss_res = sum((d - (cs_mps * t + d_prime_m)) ** 2 for t, d in efforts)
    r_squared = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot

    return CriticalSpeedFit(
        cs_mps=cs_mps,
        cs_pace_sec_per_km=1000.0 / cs_mps,
        d_prime_m=d_prime_m,
        r_squared=r_squared,
        n_points=n,
    )


def _quarter_label(date: str) -> str:
    """Map an ISO ``YYYY-MM-DD`` date to a ``YYYY-Qn`` quarter label."""
    year = int(date[:4])
    month = int(date[5:7])
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}"


def _frontier(
    efforts: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Best-effort frontier within the 2-45 min window.

    Keeps only points inside ``[2 min, 45 min]`` and drops dominated points
    (a point ``(t1, d1)`` is dominated when another ``(t2, d2)`` covers at
    least as much distance in no more time: ``t2 <= t1`` and ``d2 >= d1``).
    """
    windowed = [(t, d) for t, d in efforts if _MIN_DURATION_S <= t <= _MAX_DURATION_S]
    frontier: list[tuple[float, float]] = []
    for t1, d1 in windowed:
        dominated = any(
            (t2 <= t1 and d2 >= d1) and (t2 < t1 or d2 > d1) for t2, d2 in windowed
        )
        if not dominated:
            frontier.append((t1, d1))
    return frontier


def quarterly_critical_speed(
    per_run_efforts: list[tuple[str, float, float]],
) -> list[dict]:
    """Fit Critical Speed per calendar quarter from per-run best efforts.

    Args:
        per_run_efforts: ``(date, duration_seconds, distance_m)`` tuples, one
            per run best-effort segment. ``date`` is ISO ``YYYY-MM-DD``.

    Returns:
        One dict per quarter that has a fittable frontier (>= 2 points),
        sorted by quarter ascending, each with keys ``quarter``, ``cs_mps``,
        ``cs_pace_sec_per_km``, ``r_squared``, ``n`` and ``label``. ``D'`` is
        intentionally omitted (not a valid objective metric here).
    """
    by_quarter: dict[str, list[tuple[float, float]]] = {}
    for date, duration_s, distance_m in per_run_efforts:
        by_quarter.setdefault(_quarter_label(date), []).append((duration_s, distance_m))

    results: list[dict] = []
    for quarter in sorted(by_quarter):
        fit = fit_critical_speed(_frontier(by_quarter[quarter]))
        if fit is None:
            continue
        results.append(
            {
                "quarter": quarter,
                "cs_mps": fit.cs_mps,
                "cs_pace_sec_per_km": fit.cs_pace_sec_per_km,
                "r_squared": fit.r_squared,
                "n": fit.n_points,
                "label": fit.label,
            }
        )
    return results
