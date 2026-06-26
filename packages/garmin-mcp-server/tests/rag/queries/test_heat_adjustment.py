"""Tests for the heat-adjustment model.

Unit tests mock ``GarminDBReader`` so no real DuckDB is touched. The fit tests
feed synthetic ``HR = 140 + 0.35 * heat_hinge(temp) + noise`` data to confirm
the temperature-hinge coefficient is recovered (spike measured +0.35 bpm/°C).
The integration test runs against the real DuckDB when available and skips
gracefully otherwise.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.rag.queries.heat_adjustment import (
    REF_TEMP_C,
    HeatAdjustmentModel,
    HeatModelCoefficients,
    heat_hinge,
)

_ORIGINAL_DATA_DIR = os.environ.get("GARMIN_DATA_DIR")


def _coeffs(beta_heat: float = 0.35, ref_temp_c: float = 15.0) -> HeatModelCoefficients:
    """Build a coefficients fixture for static-method tests."""
    return HeatModelCoefficients(
        intercept=140.0,
        beta_pace=0.0,
        beta_heat=beta_heat,
        beta_days=0.0,
        ref_temp_c=ref_temp_c,
        n=60,
        r_squared=0.5,
    )


def _make_model() -> tuple[HeatAdjustmentModel, MagicMock]:
    """Build a model instance with a mocked DB reader.

    Returns the model plus the mock reader so tests can configure
    ``.return_value`` without tripping mypy on the typed ``db_reader``.
    """
    with patch("garmin_mcp.rag.queries.heat_adjustment.GarminDBReader") as mock_reader:
        model = HeatAdjustmentModel()
        reader = mock_reader.return_value
        model.db_reader = reader
        return model, reader


# --------------------------------------------------------------------------- #
# heat_hinge()
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_heat_hinge_above_ref():
    assert heat_hinge(30.0, ref_temp_c=15.0) == 15.0


@pytest.mark.unit
def test_heat_hinge_below_ref():
    assert heat_hinge(10.0, ref_temp_c=15.0) == 0.0


@pytest.mark.unit
def test_heat_hinge_at_ref():
    assert heat_hinge(15.0, ref_temp_c=15.0) == 0.0


# --------------------------------------------------------------------------- #
# HeatAdjustmentModel.heat_cost()
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_heat_cost_30c():
    cost = HeatAdjustmentModel.heat_cost(30.0, _coeffs(beta_heat=0.35))
    assert cost == pytest.approx(5.25, abs=1e-6)


@pytest.mark.unit
def test_heat_cost_at_ref():
    assert HeatAdjustmentModel.heat_cost(15.0, _coeffs(beta_heat=0.35)) == 0.0


# --------------------------------------------------------------------------- #
# HeatAdjustmentModel.climate_neutral_hr()
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_climate_neutral_hr_subtracts_heat_cost():
    neutral = HeatAdjustmentModel.climate_neutral_hr(
        150.0, 30.0, _coeffs(beta_heat=0.35)
    )
    assert neutral == pytest.approx(144.75, abs=1e-6)


@pytest.mark.unit
def test_climate_neutral_hr_no_change_below_ref():
    neutral = HeatAdjustmentModel.climate_neutral_hr(
        150.0, 10.0, _coeffs(beta_heat=0.35)
    )
    assert neutral == 150.0


# --------------------------------------------------------------------------- #
# HeatAdjustmentModel.fit()
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_fit_recovers_positive_heat_coefficient():
    """Synthetic HR = 140 + 0.35*hinge(temp) + noise → beta_heat ≈ 0.35."""
    n = 60
    rng = np.random.default_rng(42)
    temps = rng.uniform(5.0, 35.0, n)
    paces = rng.uniform(300.0, 360.0, n)
    noise = rng.normal(0.0, 1.0, n)

    base = date(2025, 4, 1)
    ids = list(range(n))
    dates = {i: (base + timedelta(days=i)).isoformat() for i in ids}
    fields = {
        i: {
            "avg_heart_rate": float(
                140.0 + 0.35 * max(temps[i] - REF_TEMP_C, 0.0) + noise[i]
            ),
            "avg_pace_seconds_per_km": float(paces[i]),
            "temp_celsius": float(temps[i]),
        }
        for i in ids
    }

    model, reader = _make_model()
    reader.get_activity_dates.return_value = dates
    reader.get_bulk_activity_fields.return_value = fields

    coeffs = model.fit(ids)

    assert coeffs.beta_heat > 0
    assert coeffs.beta_heat == pytest.approx(0.35, abs=0.1)
    assert coeffs.n == 60


@pytest.mark.unit
def test_fit_raises_on_insufficient_data():
    """Only 3 complete rows (< MIN_FIT_ACTIVITIES) → ValueError."""
    ids = [1, 2, 3]
    dates = {i: f"2025-04-0{i}" for i in ids}
    fields = {
        i: {
            "avg_heart_rate": 150.0,
            "avg_pace_seconds_per_km": 330.0,
            "temp_celsius": 20.0,
        }
        for i in ids
    }

    model, reader = _make_model()
    reader.get_activity_dates.return_value = dates
    reader.get_bulk_activity_fields.return_value = fields

    with pytest.raises(ValueError):
        model.fit(ids)


@pytest.mark.unit
def test_fit_drops_rows_with_missing_temp():
    """A temp=None row is excluded; n reflects only complete rows."""
    base = date(2025, 4, 1)
    ids = list(range(12))  # 11 complete + 1 missing temp
    dates = {i: (base + timedelta(days=i)).isoformat() for i in ids}
    fields = {}
    for i in ids:
        fields[i] = {
            "avg_heart_rate": float(150 + i),
            "avg_pace_seconds_per_km": float(330 - i),
            "temp_celsius": None if i == 5 else float(15 + i),
        }

    model, reader = _make_model()
    reader.get_activity_dates.return_value = dates
    reader.get_bulk_activity_fields.return_value = fields

    coeffs = model.fit(ids)

    assert coeffs.n == 11  # 12 ids - 1 dropped (missing temp)


# --------------------------------------------------------------------------- #
# Integration
# --------------------------------------------------------------------------- #


def _resolve_real_db_path() -> Path | None:
    """Resolve the real DuckDB path independent of test env isolation."""
    candidates: list[Path] = []
    if _ORIGINAL_DATA_DIR:
        candidates.append(
            Path(_ORIGINAL_DATA_DIR) / "database" / "garmin_performance.duckdb"
        )
    candidates.append(
        Path.home() / "garmin_data" / "data" / "database" / "garmin_performance.duckdb"
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@pytest.mark.integration
def test_e2e_compute_trend_real_db():
    """Real DuckDB running activities → status=ok, beta_heat > 0, consistent points."""
    db_path = _resolve_real_db_path()
    if db_path is None:
        pytest.skip("Real DuckDB not available; skipping integration test")

    reader = GarminDBReader(str(db_path))
    rows = reader.execute_read_query(
        "SELECT activity_id FROM activities "
        "WHERE avg_heart_rate IS NOT NULL "
        "AND avg_pace_seconds_per_km IS NOT NULL "
        "AND temp_celsius IS NOT NULL "
        "ORDER BY activity_date"
    )
    activity_ids = [int(r[0]) for r in rows]
    if len(activity_ids) < 10:
        pytest.skip(
            "Fewer than 10 complete running activities in DB; skipping integration test"
        )

    model = HeatAdjustmentModel(str(db_path))
    result = model.compute_trend(
        activity_ids, start_date="2000-01-01", end_date="2100-01-01"
    )

    assert result["status"] == "ok"
    assert result["coefficients"]["beta_heat"] > 0
    assert len(result["points"]) >= 10

    coeffs = model.fit(activity_ids)
    for point in result["points"]:
        expected_neutral = point["raw_hr"] - point["heat_cost"]
        assert point["neutral_hr"] == pytest.approx(expected_neutral, abs=1e-6)
        expected_cost = HeatAdjustmentModel.heat_cost(point["temp_c"], coeffs)
        assert point["heat_cost"] == pytest.approx(expected_cost, abs=1e-6)

    # MCP-boundary serialization must succeed.
    json.dumps(result, default=str)
