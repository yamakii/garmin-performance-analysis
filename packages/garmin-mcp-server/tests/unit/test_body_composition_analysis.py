"""Unit tests for body-composition analysis helpers (#501).

Pure functions only -- no I/O. Cover the fat/lean decomposition (good cut,
muscle-loss warning, missing body fat) and lean-mass power-to-weight.
"""

from __future__ import annotations

import pytest

from garmin_mcp.analysis.body_composition import (
    decompose_weight_change,
    lean_power_to_weight,
)


@pytest.mark.unit
def test_decompose_good_cut_fat_dominant() -> None:
    """80kg/24% -> 78.8kg/22.5%: fat ~-1.5kg, lean ~+0.3kg, no warning."""
    start = {"weight_kg": 80.0, "body_fat_pct": 24.0}
    end = {"weight_kg": 78.8, "body_fat_pct": 22.5}

    result = decompose_weight_change(start, end)

    assert result["delta_weight"] == pytest.approx(-1.2, abs=0.01)
    # start fat 19.2, end fat 17.73 -> delta_fat -1.47
    assert result["delta_fat"] == pytest.approx(-1.47, abs=0.05)
    # start lean 60.8, end lean 61.07 -> delta_lean +0.27
    assert result["delta_lean"] == pytest.approx(0.27, abs=0.05)
    assert result["muscle_loss_warning"] is False
    # Lean rose, so the cut cost no muscle.
    assert result["lean_loss_ratio"] == pytest.approx(0.0, abs=0.001)


@pytest.mark.unit
def test_decompose_muscle_loss_warning() -> None:
    """A cut where ~50% of the lost weight is lean mass flags a warning."""
    # 80kg/20% -> 78kg/19.74%:
    #   start fat 16.0, end fat ~15.40 -> delta_fat ~-0.60
    #   start lean 64.0, end lean ~62.59 -> delta_lean ~-1.41 (>50% of -2.0)
    start = {"weight_kg": 80.0, "body_fat_pct": 20.0}
    end = {"weight_kg": 78.0, "body_fat_pct": 19.74}

    result = decompose_weight_change(start, end)

    assert result["delta_weight"] == pytest.approx(-2.0, abs=0.01)
    assert result["lean_loss_ratio"] is not None
    assert result["lean_loss_ratio"] > 0.40
    assert result["muscle_loss_warning"] is True


@pytest.mark.unit
def test_decompose_handles_missing_body_fat() -> None:
    """Missing body fat on either end -> null fat/lean split, no exception."""
    start = {"weight_kg": 80.0, "body_fat_pct": None}
    end = {"weight_kg": 78.8, "body_fat_pct": 22.5}

    result = decompose_weight_change(start, end)

    # Weight delta still computed; fat/lean undefined.
    assert result["delta_weight"] == pytest.approx(-1.2, abs=0.01)
    assert result["delta_fat"] is None
    assert result["delta_lean"] is None
    assert result["lean_loss_ratio"] is None
    assert result["muscle_loss_warning"] is False


@pytest.mark.unit
def test_body_composition_delta_lean_golden() -> None:
    """Golden: 70kg->65kg at a constant 25% body fat freezes the decomposition.

    Losing weight at an unchanged body-fat percentage strips fat and lean in the
    same 25/75 proportion as the body itself. These golden constants guard the
    fat/lean split formula (``weight * bf%``) and the lean-loss-ratio coefficient
    against silent drift; recompute deliberately if the math is intentionally
    changed.

    start fat 70*0.25=17.5, lean 52.5; end fat 65*0.25=16.25, lean 48.75.
    """
    start = {"weight_kg": 70.0, "body_fat_pct": 25.0}
    end = {"weight_kg": 65.0, "body_fat_pct": 25.0}

    result = decompose_weight_change(start, end)

    assert result["delta_weight"] == pytest.approx(-5.0, abs=1e-6)
    assert result["delta_fat"] == pytest.approx(-1.25, abs=1e-6)
    assert result["delta_lean"] == pytest.approx(-3.75, abs=1e-6)
    # 3.75 of the 5.0 kg lost is lean mass -> 0.75 lean-loss ratio.
    assert result["lean_loss_ratio"] == pytest.approx(0.75, abs=1e-6)
    assert result["muscle_loss_warning"] is True


@pytest.mark.unit
def test_lean_pwr_basic() -> None:
    """ftp=337, weight=78.8, fat=22.5 -> ~5.52 W/kg (lean ~61.07kg)."""
    result = lean_power_to_weight(ftp_w=337.0, weight_kg=78.8, body_fat_pct=22.5)
    assert result == pytest.approx(5.52, abs=0.02)


@pytest.mark.unit
def test_lean_pwr_missing_inputs_returns_none() -> None:
    """Any missing input -> None (null-safe)."""
    assert lean_power_to_weight(None, 78.8, 22.5) is None
    assert lean_power_to_weight(337.0, None, 22.5) is None
    assert lean_power_to_weight(337.0, 78.8, None) is None
