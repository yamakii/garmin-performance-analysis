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

``fit_weight_economy_model`` adds a longitudinal OLS (``EF ~ weight + days
(+ fitness)``) over the coupled records (#553). It reports the weight coefficient,
its p-value, R^2 and the effect size (delta EF per 5 kg lost), plus a
multicollinearity flag (VIF) so single-year windows -- where weight and time are
nearly collinear -- are reported as *association*, not a clean causal coefficient.
statsmodels is not a dependency; coefficients come from ``numpy.linalg.lstsq`` and
p-values from ``scipy.stats``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray
from scipy import stats

# Maximum allowed gap (days) between a run and the nearest weight measurement.
# spike (#525) showed a median join gap of 0 days; 14 days keeps n high while
# avoiding stale weights.
DEFAULT_MAX_GAP_DAYS = 14

# Inf-safe sentinel VIF for a perfectly collinear / constant covariate (1/0 -> inf).
_LARGE_VIF = 1e9


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


@dataclass(frozen=True)
class CovariateResult:
    """OLS result for a single explanatory variable."""

    coef: float
    p_value: float
    vif: float  # variance-inflation factor of this explanatory variable


@dataclass(frozen=True)
class WeightEconomyModel:
    """Longitudinal OLS ``EF ~ weight + days (+ fitness)`` summary."""

    n: int
    r_squared: float
    weight: CovariateResult  # weight coef on EF (physiologically negative)
    days: CovariateResult
    fitness: CovariateResult | None  # only when a fitness covariate is provided
    delta_ef_per_5kg_loss: float  # = -weight.coef * 5 (positive when coef negative)
    collinearity_flag: bool  # any explanatory VIF >= vif_threshold
    note: str  # association / collinearity caveat


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


def _ols_r_squared(x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    """R^2 of the OLS fit of ``y`` on design matrix ``x`` (intercept included).

    Returns 1.0 when ``y`` is constant (zero total variance), which drives the
    VIF of a constant covariate to the inf-safe sentinel.
    """
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot <= 0.0:
        return 1.0
    return 1.0 - ss_res / ss_tot


def _vif_per_covariate(matrix: NDArray[np.float64]) -> list[float]:
    """VIF for each column of the explanatory matrix ``matrix`` (no intercept).

    VIF_j = 1 / (1 - R^2_j), where R^2_j regresses covariate ``j`` on an
    intercept plus the other covariates. A constant or perfectly collinear
    covariate (denominator ~ 0) maps to ``_LARGE_VIF`` instead of dividing by
    zero.
    """
    n, p = matrix.shape
    intercept = np.ones((n, 1))
    vifs: list[float] = []
    for j in range(p):
        y_j = matrix[:, j]
        others = np.delete(matrix, j, axis=1)
        x_j = np.hstack([intercept, others])
        r2 = _ols_r_squared(x_j, y_j)
        denom = 1.0 - r2
        vifs.append(_LARGE_VIF if denom <= 1e-12 else 1.0 / denom)
    return vifs


def fit_weight_economy_model(
    records: list[CoupledRecord],
    fitness_by_activity: dict[int, float] | None = None,
    vif_threshold: float = 5.0,
) -> WeightEconomyModel:
    """Fit ``EF ~ weight + days (+ fitness)`` by OLS over coupled records.

    The response is each record's EF. ``days`` is the integer day offset from the
    earliest run date (the time covariate). When ``fitness_by_activity`` is given
    it adds a third explanatory variable keyed by ``activity_id``; otherwise the
    model has two covariates and ``fitness`` is ``None``.

    Coefficients come from ``numpy.linalg.lstsq`` and p-values from a two-sided
    OLS t-test (``scipy.stats``). A per-covariate VIF flags multicollinearity:
    when any explanatory VIF is ``>= vif_threshold`` the weight coefficient is
    reported as an *association* rather than an identified causal effect.

    Args:
        records: Coupled run/weight records (need >= n_params + 2).
        fitness_by_activity: Optional fitness covariate (e.g. VO2max) per
            ``activity_id``. ``None`` => 2 covariates, ``fitness=None``.
        vif_threshold: VIF at/above which collinearity is flagged.

    Returns:
        A :class:`WeightEconomyModel` with coefficients, p-values, R^2, the
        5 kg-loss effect size and the collinearity flag/note.

    Raises:
        ValueError: When too few records are supplied
            (``n < n_params + 2`` with ``n_params = intercept + covariates``).
    """
    has_fitness = fitness_by_activity is not None
    covariate_names = ["weight", "days"] + (["fitness"] if has_fitness else [])
    n = len(records)
    n_params = 1 + len(covariate_names)  # intercept + covariates
    if n < n_params + 2:
        raise ValueError(
            f"Too few records ({n}) for {n_params} params "
            f"(intercept + {len(covariate_names)} covariates); need >= {n_params + 2}"
        )

    earliest = min(r.run_date for r in records)
    y = np.array([r.ef for r in records], dtype=np.float64)
    weight_col = np.array([r.weight_kg for r in records], dtype=np.float64)
    days_col = np.array(
        [(r.run_date - earliest).days for r in records], dtype=np.float64
    )
    cols: list[NDArray[np.float64]] = [weight_col, days_col]
    if has_fitness:
        assert fitness_by_activity is not None  # for type narrowing
        cols.append(
            np.array(
                [fitness_by_activity[r.activity_id] for r in records],
                dtype=np.float64,
            )
        )
    explanatory = np.column_stack(cols)  # n x p, no intercept
    design = np.hstack([np.ones((n, 1)), explanatory])  # n x (p + 1)

    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0

    df = n - design.shape[1]
    sigma2 = ss_res / df if df > 0 else 0.0
    xtx_inv = np.linalg.inv(design.T @ design)
    se = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_stats = np.where(se > 0.0, beta / se, 0.0)
    p_values = 2.0 * stats.t.sf(np.abs(t_stats), df)

    vifs = _vif_per_covariate(explanatory)

    results: dict[str, CovariateResult] = {}
    for idx, name in enumerate(covariate_names):
        param_idx = idx + 1  # skip the intercept at index 0
        results[name] = CovariateResult(
            coef=float(beta[param_idx]),
            p_value=float(p_values[param_idx]),
            vif=float(vifs[idx]),
        )

    collinearity_flag = any(v >= vif_threshold for v in vifs)
    delta_ef_per_5kg_loss = -results["weight"].coef * 5.0
    if collinearity_flag:
        note = (
            "association (causal coef not identified due to collinearity); "
            "weight effect is entangled with time/fitness in this window"
        )
    else:
        note = (
            "association with effect-size estimate (no collinearity detected); "
            "interpret the weight coefficient as an association, not an isolated "
            "causal effect"
        )

    return WeightEconomyModel(
        n=n,
        r_squared=r_squared,
        weight=results["weight"],
        days=results["days"],
        fitness=results.get("fitness"),
        delta_ef_per_5kg_loss=delta_ef_per_5kg_loss,
        collinearity_flag=collinearity_flag,
        note=note,
    )
