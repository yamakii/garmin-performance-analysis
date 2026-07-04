"""Tests for the composite injury-risk score (#717).

Unit tests cover the pure ``compute_injury_risk`` fusion (band classification,
ACWR piecewise contribution, missing-input renormalization, all-missing
short-circuit). One integration test drives the ``GarminDBReader.get_injury_risk``
facade against a generated verification DB to prove the wiring returns a
JSON-serializable result with a valid band.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.analysis.injury_risk import (
    _form_factor,
    _form_ratio_to_risk,
    classify_band,
    compute_injury_risk,
)

# Reusable healthy inputs (no risk contribution).
_ACWR_HEALTHY: dict[str, Any] = {"acwr": 1.0, "status": "optimal"}
_DURABILITY_STABLE: dict[str, Any] = {"trend": {"direction": "stable"}}
_WELLNESS_HEALTHY: dict[str, Any] = {
    "date": "2025-03-01",
    "hrv": {"flag": "within", "adverse": False},
    "readiness": {"flag": "within", "adverse": False},
    "rhr": {"flag": "within", "adverse": False},
    "overall_flag": False,
}
# Healthy form signal: recent event rate well within the personal baseline
# (ratio 0.5 <= 1.2 => 0 risk) but present (baseline rate above the floor).
_FORM_HEALTHY: dict[str, Any] = {"recent_rate": 1.0, "baseline_rate": 2.0}


@pytest.mark.unit
def test_injury_risk_low_all_healthy() -> None:
    """All four signals healthy -> band 'low', score < 30."""
    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=_DURABILITY_STABLE,
        wellness_deviation=_WELLNESS_HEALTHY,
        form_anomaly=_FORM_HEALTHY,
    )

    assert result["band"] == "low"
    assert result["score"] < 30
    assert set(result["available_inputs"]) == {
        "acwr",
        "durability",
        "wellness",
        "form_anomaly",
    }


@pytest.mark.unit
def test_injury_risk_high_acwr_spike() -> None:
    """An ACWR spike (1.8) with the other signals unavailable -> band 'high'.

    With only ACWR present its risk fraction (1.0) drives the renormalized
    score to 100, so ACWR is the top (only) factor.
    """
    result = compute_injury_risk(
        acwr={"acwr": 1.8, "status": "high_risk"},
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
    )

    assert result["band"] == "high"
    assert result["factors"][0]["name"] == "acwr"
    # ACWR has the maximum contribution among factors.
    assert result["factors"][0]["contribution"] == max(
        f["contribution"] for f in result["factors"]
    )


@pytest.mark.unit
def test_injury_risk_missing_input_renormalizes() -> None:
    """A missing ACWR drops out; score is computed from the remaining three."""
    result = compute_injury_risk(
        acwr=None,
        durability_trend=_DURABILITY_STABLE,
        wellness_deviation=_WELLNESS_HEALTHY,
        form_anomaly=_FORM_HEALTHY,
    )

    assert "acwr" not in result["available_inputs"]
    assert set(result["available_inputs"]) == {"durability", "wellness", "form_anomaly"}
    assert isinstance(result["score"], int)
    assert result["band"] == "low"


@pytest.mark.unit
def test_injury_risk_all_missing_insufficient() -> None:
    """Every signal missing -> {'insufficient_data': True} (no misleading zero)."""
    result = compute_injury_risk(
        acwr=None,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
    )

    assert result == {"insufficient_data": True}


@pytest.mark.unit
def test_injury_risk_band_boundaries() -> None:
    """Band boundaries: 30 -> moderate, 60 -> moderate, 61 -> high (29 -> low)."""
    assert classify_band(29) == "low"
    assert classify_band(30) == "moderate"
    assert classify_band(60) == "moderate"
    assert classify_band(61) == "high"


@pytest.mark.unit
def test_form_factor_ratio_below_safe_zero() -> None:
    """Recent rate below baseline (ratio 0.49 <= 1.2) -> 0 risk, factor present."""
    risk, detail = _form_factor({"recent_rate": 1.4, "baseline_rate": 2.85})

    assert risk == 0.0
    assert detail  # present, non-empty detail => factor is available


@pytest.mark.unit
def test_form_factor_ratio_saturates() -> None:
    """Recent rate 3x baseline (ratio 3.0 >= 2.0) saturates the factor at 1.0."""
    risk, _ = _form_factor({"recent_rate": 6.0, "baseline_rate": 2.0})

    assert risk == 1.0


@pytest.mark.unit
def test_form_factor_ratio_midpoint() -> None:
    """Ratio 1.6 (midpoint of [1.2, 2.0]) -> 0.5 risk."""
    assert _form_ratio_to_risk(1.6) == pytest.approx(0.5)

    risk, _ = _form_factor({"recent_rate": 3.2, "baseline_rate": 2.0})
    assert risk == pytest.approx(0.5)


@pytest.mark.unit
def test_form_factor_insufficient_baseline_drops() -> None:
    """A baseline rate below the 0.2 floor drops the factor (too little data)."""
    assert _form_factor({"recent_rate": 5.0, "baseline_rate": 0.1}) == (None, "")


@pytest.mark.unit
def test_form_factor_none_signal() -> None:
    """A missing signal drops the factor."""
    assert _form_factor(None) == (None, "")


@pytest.mark.unit
def test_injury_risk_form_ratio_contribution() -> None:
    """A high-ratio form signal (others missing) -> form_anomaly top, band high."""
    result = compute_injury_risk(
        acwr=None,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly={"recent_rate": 6.0, "baseline_rate": 2.0},
    )

    assert result["band"] == "high"
    assert result["factors"][0]["name"] == "form_anomaly"
    assert result["available_inputs"] == ["form_anomaly"]


@pytest.mark.integration
def test_get_injury_risk_tool_returns_serializable(tmp_path: Path) -> None:
    """The reader facade returns a JSON-serializable result with a valid band.

    Seeds the verification DB with four weekly runs so ACWR resolves to a real
    ratio (~1.0, optimal), guaranteeing at least one available factor and thus a
    concrete band rather than ``insufficient_data``.
    """
    from datetime import date, timedelta

    from garmin_mcp.database.connection import get_write_connection
    from garmin_mcp.database.db_reader import GarminDBReader
    from tests.generate_verification_db import generate_verification_db

    db_path = tmp_path / "injury_risk.duckdb"
    generate_verification_db(output_path=db_path)

    ref = date(2025, 3, 1)
    with get_write_connection(db_path=str(db_path)) as conn:
        for i in range(4):
            conn.execute(
                "INSERT INTO activities (activity_id, activity_date, "
                "total_distance_km) VALUES (?, ?, ?)",
                (900000 + i, str(ref - timedelta(days=7 * i)), 8.0),
            )

    reader = GarminDBReader(db_path=str(db_path))
    result = reader.get_injury_risk(date=str(ref))

    # Serializable across the MCP boundary.
    payload = json.loads(json.dumps(result, default=str))

    assert "acwr" in payload["available_inputs"]
    assert payload["band"] in {"low", "moderate", "high"}
    assert isinstance(payload["score"], int)
