"""Deterministic synthetic weight x running-economy datasets (#559).

Generates coupled run/weight series for the cross-cutting pipeline golden tests
(``join_runs_with_weight`` -> ``fit_weight_economy_model`` ->
``GarminDBReader.get_weight_economy_coupling``). The generator calibrates the
efficiency factor (``EF = avg_speed_ms / avg_heart_rate``) so that a ~5 kg weight
loss raises EF by ``ef_gain_per_drop`` (spike #525 golden: +0.0022 per 5 kg),
letting the regression recover ``delta_ef_per_5kg_loss ~= ef_gain_per_drop`` and a
negative weight coefficient. No real data is touched; all randomness flows from a
seeded ``numpy.random.default_rng`` so the numbers are reproducible.

Two regimes:

* ``collinear=False`` (clean multi-year window): weight values are shuffled
  relative to the run-date order, so weight and elapsed days are uncorrelated and
  the per-covariate VIF stays < 5.
* ``collinear=True`` (single-year window): weight is a near-linear function of
  elapsed days (corr > 0.95), so the weight/days VIF is >= 5 and the model reports
  an *association* rather than an isolated effect.

Each run is paired with a same-date ``WeightMeasurement`` (gap 0 days) so the
+/-14 day nearest-neighbour join keeps every run (``n_matched == n``).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from garmin_mcp.analysis.running_economy import RunRecord, WeightMeasurement

# Physiologically plausible anchors: hold HR constant and let EF (hence speed)
# track weight. EF ~ 0.017-0.019 -> speed ~ 2.47-2.78 m/s at 145 bpm.
_BASE_EF = 0.0170  # EF at the heaviest weight (weight_start_kg)
_HR = 145.0  # constant avg heart rate (bpm); EF realized purely via speed
_EF_NOISE_STD = 0.00012  # small measurement noise on EF (keeps delta in range)
_SPAN_DAYS = 350  # date span (< 52 weeks so the default reader window covers it)
_DATE_BUFFER_DAYS = 7  # latest run sits a week before today
_ACTIVITY_ID_BASE = 9_100_000  # deterministic, unique, collision-free ids


def make_coupled_dataset(
    n: int = 120,
    weight_start_kg: float = 80.0,
    weight_drop_kg: float = 5.0,
    ef_gain_per_drop: float = 0.0022,
    collinear: bool = False,  # True: weight<->days highly correlated (single year)
    seed: int = 7,
) -> tuple[list[RunRecord], list[WeightMeasurement]]:
    """Return ``(runs, measurements)`` for the pipeline golden tests.

    Args:
        n: Number of runs (and same-date weight measurements) to generate.
        weight_start_kg: Heaviest weight at the start of the trajectory.
        weight_drop_kg: Total weight lost across the series.
        ef_gain_per_drop: Target EF increase for a full ``weight_drop_kg`` loss;
            the EF/weight slope is ``-ef_gain_per_drop / 5`` so the regression
            recovers ``delta_ef_per_5kg_loss ~= ef_gain_per_drop``.
        collinear: When ``False`` weight is decoupled from elapsed days (VIF < 5);
            when ``True`` weight is a near-linear function of days (corr > 0.95,
            VIF >= 5), simulating a single-year window.
        seed: Seed for ``numpy.random.default_rng`` (determinism).

    Returns:
        ``(runs, measurements)`` where each :class:`RunRecord` has a same-date
        :class:`WeightMeasurement` (gap 0), so a +/-14 day join keeps all ``n``
        runs. EF increases as weight drops; speed/HR stay physiologically
        plausible.
    """
    rng = np.random.default_rng(seed)
    # EF change per kg of body weight (negative: lighter -> higher EF).
    coef_per_kg = -ef_gain_per_drop / 5.0

    end = date.today() - timedelta(days=_DATE_BUFFER_DAYS)
    start = end - timedelta(days=_SPAN_DAYS)
    denom = max(n - 1, 1)
    dates = [start + timedelta(days=round(i * _SPAN_DAYS / denom)) for i in range(n)]

    # Heavy -> light trajectory along the run-date order.
    trajectory = np.linspace(weight_start_kg, weight_start_kg - weight_drop_kg, n)

    if collinear:
        # Weight ~ linear in elapsed days (corr > 0.95) -> high VIF.
        weights = trajectory + rng.normal(0.0, 0.05, n)
    else:
        # Decouple weight from the day axis by shuffling the assignment -> VIF ~ 1.
        weights = trajectory[rng.permutation(n)]

    runs: list[RunRecord] = []
    measurements: list[WeightMeasurement] = []
    for i in range(n):
        weight = float(weights[i])
        ef = (
            _BASE_EF
            + coef_per_kg * (weight - weight_start_kg)
            + float(rng.normal(0.0, _EF_NOISE_STD))
        )
        runs.append(
            RunRecord(
                activity_id=_ACTIVITY_ID_BASE + i,
                run_date=dates[i],
                avg_speed_ms=ef * _HR,
                avg_heart_rate=_HR,
            )
        )
        measurements.append(WeightMeasurement(measure_date=dates[i], weight_kg=weight))
    return runs, measurements
