"""Cross-cutting weight x running-economy pipeline golden tests (#559).

Threads the synthetic dataset through every layer -- ``join_runs_with_weight``
-> ``fit_weight_economy_model`` -> ``GarminDBReader.get_weight_economy_coupling``
-- and locks in the spike (#525) golden properties: the +/-14 day join keeps the
expected count, the weight coefficient is physiologically negative, the 5 kg-loss
effect size lands in the spike range, and a single-year (collinear) window raises
the collinearity flag with an *association* note. Deterministic synthetic fixtures
only; no production data.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pytest

from garmin_mcp.analysis.running_economy import (
    fit_weight_economy_model,
    join_runs_with_weight,
)
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.db_writer import GarminDBWriter
from tests.fixtures.weight_economy_synthetic import make_coupled_dataset


@pytest.mark.unit
def test_pipeline_weight_coef_negative_and_effect_size() -> None:
    """Clean window: join -> regress -> negative weight coef and a 5 kg-loss
    effect size in the spike golden range [0.0017, 0.0027]."""
    runs, measurements = make_coupled_dataset(collinear=False)
    coupled = join_runs_with_weight(runs, measurements)
    model = fit_weight_economy_model(coupled)

    assert model.weight.coef < 0
    assert 0.0017 <= model.delta_ef_per_5kg_loss <= 0.0027


@pytest.mark.unit
def test_pipeline_clean_window_no_collinearity_flag() -> None:
    """Decoupled weight/days -> no collinearity flag and weight VIF < 5."""
    runs, measurements = make_coupled_dataset(collinear=False)
    coupled = join_runs_with_weight(runs, measurements)
    model = fit_weight_economy_model(coupled)

    assert model.collinearity_flag is False
    assert model.weight.vif < 5.0


@pytest.mark.unit
def test_pipeline_single_year_window_sets_collinearity_flag() -> None:
    """Single-year window (weight<->days corr > 0.95) -> collinearity flag set and
    an *association* note."""
    runs, measurements = make_coupled_dataset(collinear=True)
    coupled = join_runs_with_weight(runs, measurements)

    # Confirm the regime: weight and elapsed days are near-perfectly correlated.
    days = np.array([(r.run_date - coupled[0].run_date).days for r in coupled])
    weights = np.array([r.weight_kg for r in coupled])
    corr = abs(float(np.corrcoef(days, weights)[0, 1]))
    assert corr > 0.95

    model = fit_weight_economy_model(coupled)
    assert model.collinearity_flag is True
    assert "association" in model.note


@pytest.mark.unit
def test_pipeline_join_keeps_expected_count() -> None:
    """Every run has a same-date weight (gap 0) -> +/-14 day join keeps all n."""
    n = 120
    runs, measurements = make_coupled_dataset(n=n, collinear=False)
    coupled = join_runs_with_weight(runs, measurements)

    assert len(coupled) == n


def _seed_synthetic_db(db_path: Path) -> int:
    """Insert the clean-window synthetic dataset into a schema-initialized DB.

    Returns the direct ``join_runs_with_weight`` count so the test can assert the
    reader's series length matches the pure-function join.
    """
    runs, measurements = make_coupled_dataset(collinear=False)
    # Independent VO2max fitness covariate (decoupled from weight/days).
    rng = np.random.default_rng(11)
    vo2_values = 52.0 + rng.normal(0.0, 1.0, len(runs))

    GarminDBWriter(db_path=str(db_path))  # initialize schema
    conn = duckdb.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO activities "
            "(activity_id, activity_date, avg_speed_ms, avg_heart_rate) "
            "VALUES (?, ?, ?, ?)",
            [
                (r.activity_id, str(r.run_date), r.avg_speed_ms, r.avg_heart_rate)
                for r in runs
            ],
        )
        conn.executemany(
            "INSERT INTO hr_efficiency (activity_id, training_type) VALUES (?, ?)",
            [(r.activity_id, "aerobic_base") for r in runs],
        )
        conn.executemany(
            "INSERT INTO body_composition (measurement_id, date, weight_kg) "
            "VALUES (?, ?, ?)",
            [
                (idx + 1, str(m.measure_date), m.weight_kg)
                for idx, m in enumerate(measurements)
            ],
        )
        conn.executemany(
            "INSERT INTO vo2_max (activity_id, value, date) VALUES (?, ?, ?)",
            [
                (r.activity_id, float(vo2_values[i]), str(r.run_date))
                for i, r in enumerate(runs)
            ],
        )
    finally:
        conn.close()

    return len(join_runs_with_weight(runs, measurements))


@pytest.mark.integration
def test_e2e_tool_pipeline_consistency(tmp_path: Path) -> None:
    """Synthetic data through the reader matches the direct join: negative weight
    coef, series count equal to the pure-function join, json.dumps-serializable."""
    db_path = tmp_path / "pipeline.duckdb"
    expected_count = _seed_synthetic_db(db_path)

    reader = GarminDBReader(db_path=str(db_path))
    result = reader.get_weight_economy_coupling(weeks=52)

    assert result["model"] is not None
    assert result["model"]["weight"]["coef"] < 0
    assert len(result["series"]) == expected_count
    assert result["n_matched"] == expected_count

    # MCP-boundary serializable.
    json.dumps(result, default=str)
