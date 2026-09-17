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
    WEIGHTS,
    _form_factor,
    _form_ratio_to_risk,
    _symptom_factor,
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


# ---------------------------------------------------------------------------
# Symptom factor (#1223)
# ---------------------------------------------------------------------------

# A flagged status as the symptom rule returns it (right calf, acute).
_SYMPTOM_ACUTE: dict[str, Any] = {
    "date": "2026-09-18",
    "flag": True,
    "flagged_regions": [
        {
            "body_region": "calf",
            "side": "right",
            "rule": "acute",
            "latest_severity": 6,
            "latest_date": "2026-09-18",
            "reports": [{"date": "2026-09-18", "severity": 6}],
        }
    ],
    "asked_today": True,
    "clear_today": False,
    "recently_cleared": False,
    "days_since_last_report": 0,
    "reason_ja": "右ふくらはぎ: 9/18 6/10（7日以内に5以上）→ 処方の見直しを推奨",
}

# Asked and clear: reports exist in the window, none of them flag.
_SYMPTOM_CLEAR: dict[str, Any] = {
    "date": "2026-09-18",
    "flag": False,
    "flagged_regions": [],
    "asked_today": True,
    "clear_today": True,
    "recently_cleared": True,
    "days_since_last_report": 0,
    "reason_ja": "今日の申告は痛みなし（フラグなし）",
}


@pytest.mark.unit
def test_symptom_factor_unavailable_without_rows() -> None:
    """Nothing logged in 14 days -> the factor is dropped, not read as zero."""
    never_asked: dict[str, Any] = {
        "date": "2026-09-18",
        "flag": False,
        "flagged_regions": [],
        "asked_today": False,
        "clear_today": False,
        "recently_cleared": False,
        "days_since_last_report": None,
        "reason_ja": "直近14日の症状記録なし（未確認）",
    }

    assert _symptom_factor(never_asked) == (None, "")
    assert _symptom_factor(None) == (None, "")

    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        symptom=never_asked,
    )
    assert "symptom" not in result["available_inputs"]


@pytest.mark.unit
def test_symptom_acute_contribution() -> None:
    """rule='acute' -> risk 1.0, contributing its renormalized weight."""
    risk, detail = _symptom_factor(_SYMPTOM_ACUTE)
    assert risk == 1.0
    assert "右ふくらはぎ" in detail

    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        symptom=_SYMPTOM_ACUTE,
    )

    assert set(result["available_inputs"]) == {"acwr", "symptom"}
    expected = WEIGHTS["symptom"] / (WEIGHTS["symptom"] + WEIGHTS["acwr"]) * 1.0 * 100
    symptom_factor = next(f for f in result["factors"] if f["name"] == "symptom")
    assert symptom_factor["contribution"] == pytest.approx(round(expected, 1))
    assert result["factors"][0]["name"] == "symptom"


@pytest.mark.unit
def test_symptom_consecutive_is_partial_risk() -> None:
    """rule='consecutive' is a strong warning (0.7), not a saturated factor."""
    consecutive: dict[str, Any] = {
        **_SYMPTOM_ACUTE,
        "flagged_regions": [
            {**_SYMPTOM_ACUTE["flagged_regions"][0], "rule": "consecutive"}
        ],
    }

    risk, _ = _symptom_factor(consecutive)
    assert risk == pytest.approx(0.7)


@pytest.mark.unit
def test_symptom_clear_contributes_zero_but_stays_available() -> None:
    """An explicit all-clear is evidence: risk 0.0 with the factor present."""
    risk, detail = _symptom_factor(_SYMPTOM_CLEAR)

    assert risk == 0.0
    assert detail

    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        symptom=_SYMPTOM_CLEAR,
    )
    assert "symptom" in result["available_inputs"]
    assert result["score"] == 0


@pytest.mark.unit
def test_weights_sum_to_one() -> None:
    """The weight table stays normalized as factors are added (#1222 / #1223)."""
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
