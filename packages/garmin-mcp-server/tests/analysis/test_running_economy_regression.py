"""Tests for the longitudinal weight x running-economy regression (#553).

Pure numpy/scipy OLS (``EF ~ weight + days (+ fitness)``); no I/O, no production
data. Synthetic records are built deterministically with
``numpy.random.default_rng(seed)`` so coefficient/VIF assertions are stable. The
integration test asserts the model survives ``json.dumps`` across the MCP
boundary.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

import numpy as np
import pytest

from garmin_mcp.analysis.running_economy import (
    CoupledRecord,
    fit_weight_economy_model,
)

# --- helpers --------------------------------------------------------------

_BASE_DATE = date(2024, 1, 1)
# EF slope: +5 kg of body weight lowers EF by 0.0022 -> -0.00044 EF per kg.
_EF_SLOPE_PER_KG = -0.0022 / 5.0
_EF_BASE = 0.05


def _make_records(
    weights: np.ndarray,
    days_offsets: np.ndarray,
    efs: np.ndarray,
) -> list[CoupledRecord]:
    """Build CoupledRecord rows with controlled weight / EF / run_date."""
    records: list[CoupledRecord] = []
    for i in range(len(weights)):
        ef = float(efs[i])
        records.append(
            CoupledRecord(
                activity_id=1000 + i,
                run_date=_BASE_DATE + timedelta(days=int(days_offsets[i])),
                weight_kg=float(weights[i]),
                weight_gap_days=0,
                ef=ef,
                avg_heart_rate=145.0,
                avg_speed_ms=ef * 145.0,
            )
        )
    return records


# --- fit_weight_economy_model() -------------------------------------------


@pytest.mark.unit
def test_fit_weight_coef_sign_and_effect_size() -> None:
    """Weight->EF slope is recovered: coef<0, +0.0022 per 5 kg lost, R^2>0.9."""
    rng = np.random.default_rng(42)
    n = 80
    weights = rng.uniform(70.0, 85.0, n)
    days = rng.uniform(0.0, 364.0, n)  # time independent of weight
    efs = _EF_BASE + _EF_SLOPE_PER_KG * weights + rng.normal(0.0, 0.00012, n)

    model = fit_weight_economy_model(_make_records(weights, days, efs))

    assert model.weight.coef < 0.0
    assert model.delta_ef_per_5kg_loss == pytest.approx(0.0022, abs=2e-4)
    assert model.r_squared > 0.9


@pytest.mark.unit
def test_fit_collinearity_flag_fires() -> None:
    """Weight nearly collinear with time -> flag True, VIF>=5, association note."""
    rng = np.random.default_rng(7)
    n = 40
    days = np.arange(n, dtype=float) * 9.0  # single-year window, 0..351 days
    weights = 85.0 - 0.02 * days + rng.normal(0.0, 0.3, n)  # corr(weight, days)>0.95
    efs = _EF_BASE + _EF_SLOPE_PER_KG * weights + rng.normal(0.0, 0.0002, n)

    # Sanity: the synthetic weight/time correlation is indeed near-perfect.
    assert abs(np.corrcoef(weights, days)[0, 1]) > 0.95

    model = fit_weight_economy_model(_make_records(weights, days, efs))

    assert model.collinearity_flag is True
    assert model.weight.vif >= 5.0
    assert "association" in model.note


@pytest.mark.unit
def test_fit_no_collinearity_clean_window() -> None:
    """Weight independent of time -> no collinearity flag, weight VIF<5."""
    rng = np.random.default_rng(11)
    n = 60
    weights = rng.uniform(70.0, 85.0, n)
    days = rng.uniform(0.0, 364.0, n)  # independent of weight
    efs = _EF_BASE + _EF_SLOPE_PER_KG * weights + rng.normal(0.0, 0.0002, n)

    model = fit_weight_economy_model(_make_records(weights, days, efs))

    assert model.collinearity_flag is False
    assert model.weight.vif < 5.0


@pytest.mark.unit
def test_fit_with_fitness_covariate() -> None:
    """Passing a fitness covariate -> fitness present, weight coef stays negative."""
    rng = np.random.default_rng(21)
    n = 60
    weights = rng.uniform(70.0, 85.0, n)
    days = rng.uniform(0.0, 364.0, n)
    fitness = rng.uniform(45.0, 55.0, n)  # e.g. VO2max
    efs = (
        _EF_BASE
        + _EF_SLOPE_PER_KG * weights
        + 0.0003 * (fitness - 50.0)
        + rng.normal(0.0, 0.0002, n)
    )

    records = _make_records(weights, days, efs)
    fitness_by_activity = {
        rec.activity_id: float(fitness[i]) for i, rec in enumerate(records)
    }

    model = fit_weight_economy_model(records, fitness_by_activity=fitness_by_activity)

    assert model.fitness is not None
    assert model.weight.coef < 0.0


@pytest.mark.unit
def test_fit_insufficient_samples_raises() -> None:
    """3 records with 3 covariates (need >= 6) -> ValueError."""
    rng = np.random.default_rng(99)
    n = 3
    weights = np.array([80.0, 81.0, 82.0])
    days = np.array([0.0, 30.0, 60.0])
    fitness = np.array([50.0, 49.0, 51.0])
    efs = _EF_BASE + _EF_SLOPE_PER_KG * weights + rng.normal(0.0, 0.0002, n)

    records = _make_records(weights, days, efs)
    fitness_by_activity = {
        rec.activity_id: float(fitness[i]) for i, rec in enumerate(records)
    }

    with pytest.raises(ValueError):
        fit_weight_economy_model(records, fitness_by_activity=fitness_by_activity)


# --- integration ----------------------------------------------------------


@pytest.mark.integration
def test_e2e_model_serializable() -> None:
    """Model survives json.dumps(asdict(...)) (MCP boundary); fields non-null."""
    rng = np.random.default_rng(123)
    n = 50
    weights = rng.uniform(70.0, 85.0, n)
    days = rng.uniform(0.0, 364.0, n)
    efs = _EF_BASE + _EF_SLOPE_PER_KG * weights + rng.normal(0.0, 0.0002, n)

    model = fit_weight_economy_model(_make_records(weights, days, efs))

    serialized = json.dumps(asdict(model), default=str)
    assert serialized  # non-empty, no exception

    payload = json.loads(serialized)
    # All non-fitness fields are non-null; fitness=None is allowed for 2 covariates.
    assert payload["n"] == n
    assert payload["r_squared"] is not None
    assert payload["weight"]["coef"] is not None
    assert payload["days"]["coef"] is not None
    assert payload["delta_ef_per_5kg_loss"] is not None
    assert payload["collinearity_flag"] is not None
    assert payload["note"]
    assert payload["fitness"] is None
