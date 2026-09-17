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
    _event_window_factor,
    _form_factor,
    _form_ratio_to_risk,
    _recovery_cost_factor,
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


# ---------------------------------------------------------------------------
# Post-event window + recovery cost factors (#1222)
# ---------------------------------------------------------------------------


def _event_window(
    verdict: str, in_window: bool = True, **overrides: Any
) -> dict[str, Any]:
    """A ``get_post_event_window`` payload with the 2025-12-29 shape."""
    payload: dict[str, Any] = {
        "date": "2025-12-29",
        "last_event": {
            "date": "2025-12-14",
            "source": "goal",
            "label": "ハーフマラソン",
            "activity_id": None,
        },
        "days_since_event": 15,
        "in_window": in_window,
        "ceiling_km": 21.2,
        "longest_since_km": 28.6,
        "longest_since_activity_id": 777001,
        "overshoot_pct": 34.9,
        "verdict": verdict,
        "reason_ja": "保護期間中に上限を超えています。",
    }
    payload.update(overrides)
    return payload


def _recovery_cost(criteria_fired: int, **overrides: Any) -> dict[str, Any]:
    """A ``get_long_run_recovery_cost`` payload with ``criteria_fired`` fired."""
    payload: dict[str, Any] = {
        "activity_id": 777001,
        "activity_date": "2025-12-29",
        "distance_km": 28.6,
        "criteria_fired": criteria_fired,
        "cost_flag": criteria_fired >= 2,
        "insufficient_data": False,
        "reason_ja": "翌朝コスト",
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_event_window_red_dominates() -> None:
    """An in-window 'red' saturates its factor even with a safe ACWR.

    ACWR 1.1 is inside the safe zone (0 risk), so the whole score comes from
    the event window: its 0.15 weight renormalized over the 0.40 available
    (acwr + event_window) times 1.0 -> 37.5 points, band 'moderate'.
    """
    risk, detail = _event_window_factor(_event_window("red"))
    assert risk == 1.0
    assert "28.6" in detail and "21.2" in detail

    result = compute_injury_risk(
        acwr={"acwr": 1.1, "status": "optimal"},
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        event_window=_event_window("red"),
    )

    assert set(result["available_inputs"]) == {"acwr", "event_window"}
    window_factor = next(f for f in result["factors"] if f["name"] == "event_window")
    expected = (
        WEIGHTS["event_window"] / (WEIGHTS["event_window"] + WEIGHTS["acwr"]) * 100
    )
    assert window_factor["contribution"] == pytest.approx(round(expected, 1))
    assert window_factor["contribution"] == pytest.approx(37.5)
    assert window_factor["detail_ja"]
    assert result["band"] == "moderate"


@pytest.mark.unit
def test_in_window_green_adds_quarter() -> None:
    """Being inside the window is itself a risk state: green contributes 0.25."""
    risk, _ = _event_window_factor(_event_window("green"))
    assert risk == pytest.approx(0.25)

    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        event_window=_event_window("green"),
    )

    expected = (
        WEIGHTS["event_window"]
        / (WEIGHTS["event_window"] + WEIGHTS["acwr"])
        * 0.25
        * 100
    )
    window_factor = next(f for f in result["factors"] if f["name"] == "event_window")
    assert window_factor["contribution"] == pytest.approx(round(expected, 1))

    # Outside the window (and with no event at all) the factor is present at 0.
    assert _event_window_factor(_event_window("green", in_window=False))[0] == 0.0
    assert _event_window_factor(_event_window("no_event"))[0] == 0.0
    # An unjudgeable window drops out rather than reading as safe.
    assert _event_window_factor(_event_window("insufficient_data")) == (None, "")
    assert _event_window_factor(None) == (None, "")


@pytest.mark.unit
def test_recovery_cost_scales_with_criteria() -> None:
    """The factor is the share of the three morning criteria that fired."""
    assert _recovery_cost_factor(_recovery_cost(0))[0] == pytest.approx(0.0)
    assert _recovery_cost_factor(_recovery_cost(2))[0] == pytest.approx(0.67, abs=0.01)
    assert _recovery_cost_factor(_recovery_cost(3))[0] == pytest.approx(1.0)

    risk, detail = _recovery_cost_factor(_recovery_cost(2))
    assert "2/3" in detail

    # An unmeasured morning is not evidence of a cheap long run.
    assert _recovery_cost_factor(_recovery_cost(2, insufficient_data=True)) == (
        None,
        "",
    )
    assert _recovery_cost_factor(None) == (None, "")

    result = compute_injury_risk(
        acwr=_ACWR_HEALTHY,
        durability_trend=None,
        wellness_deviation=None,
        form_anomaly=None,
        recovery_cost=_recovery_cost(2),
    )
    expected = (
        WEIGHTS["recovery_cost"]
        / (WEIGHTS["recovery_cost"] + WEIGHTS["acwr"])
        * (2 / 3)
        * 100
    )
    cost_factor = next(f for f in result["factors"] if f["name"] == "recovery_cost")
    assert cost_factor["contribution"] == pytest.approx(round(expected, 1))


@pytest.mark.unit
def test_new_inputs_default_none_keeps_legacy_score() -> None:
    """Four legacy inputs only -> the pre-#1222 four-factor renormalization."""
    legacy = compute_injury_risk(
        acwr={"acwr": 1.5, "status": "caution"},
        durability_trend={"trend": {"direction": "worsening"}},
        wellness_deviation=_WELLNESS_HEALTHY,
        form_anomaly=_FORM_HEALTHY,
    )
    explicit = compute_injury_risk(
        acwr={"acwr": 1.5, "status": "caution"},
        durability_trend={"trend": {"direction": "worsening"}},
        wellness_deviation=_WELLNESS_HEALTHY,
        form_anomaly=_FORM_HEALTHY,
        event_window=None,
        recovery_cost=None,
    )

    assert legacy == explicit
    assert set(legacy["available_inputs"]) == {
        "acwr",
        "durability",
        "wellness",
        "form_anomaly",
    }
    # Only ACWR (0.5 risk) and durability (1.0) carry risk, renormalized over
    # the four available weights.
    available = sum(
        WEIGHTS[name] for name in ("acwr", "durability", "wellness", "form_anomaly")
    )
    expected_score = (
        WEIGHTS["acwr"] / available * 0.5 + WEIGHTS["durability"] / available * 1.0
    ) * 100
    assert legacy["score"] == int(round(expected_score))


@pytest.mark.unit
def test_2025_12_29_scenario_is_high() -> None:
    """The 2025-12-29 precursor (post-race +35% long run) reads 'high'."""
    result = compute_injury_risk(
        acwr={"acwr": 1.8, "status": "high_risk"},
        durability_trend=None,
        wellness_deviation={
            "date": "2025-12-30",
            "hrv": {"flag": "below", "adverse": True},
            "readiness": {"flag": "below", "adverse": True},
            "rhr": {"flag": "within", "adverse": False},
            "overall_flag": True,
        },
        form_anomaly=None,
        event_window=_event_window("red"),
        recovery_cost=_recovery_cost(3),
    )

    assert set(result["available_inputs"]) == {
        "acwr",
        "event_window",
        "recovery_cost",
        "wellness",
    }
    assert result["band"] == "high"
    assert result["score"] > 90
    assert {f["name"] for f in result["factors"][:3]} == {
        "acwr",
        "event_window",
        "recovery_cost",
    }


@pytest.mark.integration
def test_reader_picks_latest_long_run_within_14_days(initialized_db_path: Path) -> None:
    """The recovery-cost factor follows the latest long run in the window."""
    from datetime import date, timedelta

    from garmin_mcp.database.connection import get_write_connection
    from garmin_mcp.database.db_reader import GarminDBReader

    ref = date(2026, 3, 1)
    with get_write_connection(db_path=str(initialized_db_path)) as conn:
        # A 25 km long run 12 days ago and a 5 km jog yesterday.
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, "
            "total_distance_km) VALUES (?, ?, ?)",
            (910001, str(ref - timedelta(days=12)), 25.0),
        )
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, "
            "total_distance_km) VALUES (?, ?, ?)",
            (910002, str(ref - timedelta(days=1)), 5.0),
        )

    reader = GarminDBReader(db_path=str(initialized_db_path))
    cost = reader._recent_long_run_recovery_cost(str(ref))

    assert cost is not None
    assert cost["activity_id"] == 910001

    # With the long run outside the 14-day window there is nothing to judge, so
    # the factor is absent from the score's inputs.
    later = str(ref + timedelta(days=10))
    assert reader._recent_long_run_recovery_cost(later) is None
    assert "recovery_cost" not in reader.get_injury_risk(date=later).get(
        "available_inputs", []
    )
