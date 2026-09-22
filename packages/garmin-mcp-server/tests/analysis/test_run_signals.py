"""Tests for the per-run signal builders (#1248).

History fixtures reuse the exactly-known robust shape from
``test_normal_range``: a block of ten values whose median is 0 and whose MAD is
1 shape unit, so a history of 10 / 20 / 30 runs has a band centre of exactly 0
and a spread of exactly the number asked for. That keeps the display-unit
assertions (``257 ms +/- 2 * 0.8 %``) exact rather than eyeballed.
"""

import json
from datetime import date, timedelta
from typing import Any

import numpy as np
import pytest

from garmin_mcp.analysis import run_signals
from garmin_mcp.analysis.normal_range import MAD_SCALE, compute_band
from garmin_mcp.analysis.run_signals import (
    REASON_EXTRAPOLATED,
    REASON_HOT,
    REASON_LOW_JUDGED_SHARE,
    REASON_NO_HR_MODEL,
    REASON_SHORT_RUN,
    REASON_THIN_BASELINE,
    build_signals,
)
from garmin_mcp.rag.queries.heat_adjustment import HeatModelCoefficients

_TODAY = date(2026, 9, 19)

# Same shape as test_normal_range: median 0, median(|value|) 1.
_SHAPE = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.0, 0.5, 1.0, 1.5, 2.0)

# Model whose expected HR for the fixture run (pace 330 s/km, 18 °C) is
# 100 + 0.1 * 330 + 1.0 * (18 - 15) = 136 bpm, with no time trend.
_COEFFS = HeatModelCoefficients(
    intercept=100.0,
    beta_pace=0.1,
    beta_heat=1.0,
    beta_days=0.0,
    ref_temp_c=15.0,
    n=30,
    r_squared=0.5,
)


# What each parameterised reason interpolates, for the registry test below. A
# reason that grows a placeholder without an entry here raises rather than
# silently printing a brace to the reader.
_REASON_PARAMS: dict[str, dict[str, Any]] = {
    REASON_SHORT_RUN: {"n": 2, "required": 3},
    REASON_THIN_BASELINE: {"n": 0, "required": 10},
    REASON_HOT: {"temp": 31.0},
    REASON_LOW_JUDGED_SHARE: {"pct": 40, "required": 50},
}


def _shaped(index: int, spread: float) -> float:
    """The ``index``-th baseline value of a series with the given robust spread."""
    return spread * _SHAPE[index % len(_SHAPE)] / MAD_SCALE


def _run(days_ago: int, **overrides: Any) -> dict[str, Any]:
    """A complete, unremarkable easy run ``days_ago`` before today."""
    row: dict[str, Any] = {
        "activity_date": _TODAY - timedelta(days=days_ago),
        "n_valid_splits": 8,
        "intensity_category": "easy",
        "gct_delta_pct": 0.0,
        "gct_ms_expected": 257.0,
        "gct_ms_actual": 257.0,
        "vo_delta_cm": 0.0,
        "vo_cm_expected": 8.0,
        "vo_cm_actual": 8.0,
        "vr_delta_pct": 0.0,
        "vr_pct_expected": 7.0,
        "vr_pct_actual": 7.0,
        "cadence_delta_pct": 0.0,
        "cadence_expected": 175.0,
        "cadence_actual": 175.0,
        "power_efficiency_score": 1.0,
        "hr_drift_percentage": 4.0,
        "avg_hr": 140.0,
        "pace": 330.0,
        "temp": 18.0,
    }
    row.update(overrides)
    return row


def _history(count: int = 30, first_days_ago: int = 1) -> list[dict[str, Any]]:
    """``count`` prior runs whose every metric has a known centre and spread."""
    rows = []
    for index in range(count):
        days_ago = first_days_ago + index
        rows.append(
            _run(
                days_ago,
                gct_delta_pct=_shaped(days_ago, 0.8),
                vo_delta_cm=_shaped(days_ago, 0.08),
                vr_delta_pct=_shaped(days_ago, 0.8),
                cadence_delta_pct=_shaped(days_ago, 0.6),
                power_efficiency_score=1.0 + _shaped(days_ago, 0.02),
                hr_drift_percentage=4.0 + _shaped(days_ago, 1.5),
                avg_hr=140.0 + _shaped(days_ago, 2.0),
            )
        )
    return rows


def _signal(signals: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    """The one signal for ``metric`` (fails loudly when the set changes)."""
    matches = [s for s in signals if s["metric"] == metric]
    assert len(matches) == 1, f"expected exactly one {metric} signal, got {matches}"
    return matches[0]


# --------------------------------------------------------------------------- #
# Shape of the result
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_every_metric_is_reported_once():
    signals = build_signals(_run(0), _history(), hr_model=_COEFFS)

    assert [s["metric"] for s in signals] == [
        "gct",
        "vo",
        "vr",
        "cadence",
        "power",
        "hr_vs_expected",
        "hr_drift",
    ]
    assert {s["family"] for s in signals} == {"form", "cardio"}


# --------------------------------------------------------------------------- #
# Form signals
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_short_run_signals_are_insufficient():
    """A 2-split run has no form average worth judging."""
    signals = build_signals(_run(0, n_valid_splits=2), _history(), hr_model=_COEFFS)

    form = [s for s in signals if s["family"] == "form"]
    assert len(form) == 5
    for signal in form:
        assert signal["status"] == "insufficient", signal["metric"]
        assert signal["z"] is None
        assert signal["adverse"] is False
        assert signal["streak"] == 0
        assert signal["reason_code"] == REASON_SHORT_RUN
        assert signal["reason"] == "有効なスプリットが 2 本で、判定には 3 本以上が必要"


@pytest.mark.unit
def test_extrapolated_form_is_not_judged():
    signals = build_signals(
        _run(0, gct_extrapolated=True), _history(), hr_model=_COEFFS
    )

    gct = _signal(signals, "gct")
    assert gct["status"] == "insufficient"
    assert gct["reason"] == "学習した速度の範囲から大きく外れているため参考値"
    assert gct["reason_code"] == REASON_EXTRAPOLATED
    # Only the extrapolated metric is withheld.
    assert _signal(signals, "cadence")["status"] != "insufficient"


@pytest.mark.unit
def test_form_normal_range_is_in_display_units():
    """The page prints "257 ms, usual 253-261", not a z-score."""
    signals = build_signals(_run(0), _history(), hr_model=_COEFFS)

    gct = _signal(signals, "gct")
    assert gct["unit"] == "ms"
    assert gct["today"] == pytest.approx(257.0)
    assert gct["expected"] == pytest.approx(257.0)
    # centre 0.0 %, spread 0.8 % -> 257 * (1 -/+ 2 * 0.8 %)
    assert gct["normal_low"] == pytest.approx(252.9, abs=0.1)
    assert gct["normal_high"] == pytest.approx(261.1, abs=0.1)
    assert gct["status"] == "within"
    assert gct["z"] == pytest.approx(0.0)


@pytest.mark.unit
def test_vo_deviation_is_relative_to_the_expected_amplitude():
    """VO's stored delta is in cm, so the band is built on delta / expected."""
    # The band is +/- 2 * 1 % of an 8 cm expectation, i.e. 7.84-8.16 cm, printed
    # at the 1 dp Garmin itself uses for vertical oscillation.
    signals = build_signals(
        _run(0, vo_delta_cm=0.2, vo_cm_actual=8.2), _history(), hr_model=_COEFFS
    )

    vo = _signal(signals, "vo")
    assert vo["unit"] == "cm"
    assert vo["normal_low"] == pytest.approx(7.8, abs=0.05)
    assert vo["normal_high"] == pytest.approx(8.2, abs=0.05)
    assert vo["z"] == pytest.approx(2.5)
    assert vo["status"] == "outside"
    assert vo["adverse"] is True
    assert vo["direction"] == "high"


@pytest.mark.unit
def test_low_cadence_is_the_adverse_side():
    signals = build_signals(
        _run(0, cadence_delta_pct=-1.5, cadence_actual=172.4),
        _history(),
        hr_model=_COEFFS,
    )

    cadence = _signal(signals, "cadence")
    assert cadence["z"] == pytest.approx(2.5)
    assert cadence["status"] == "outside"
    assert cadence["adverse"] is True
    assert cadence["direction"] == "low"
    assert cadence["normal_low"] < 175.0 < cadence["normal_high"]


@pytest.mark.unit
def test_power_efficiency_is_read_as_a_percentage():
    signals = build_signals(_run(0), _history(), hr_model=_COEFFS)

    power = _signal(signals, "power")
    assert power["unit"] == "%"
    assert power["today"] == pytest.approx(100.0)
    assert power["normal_low"] == pytest.approx(96.0, abs=0.1)
    assert power["normal_high"] == pytest.approx(104.0, abs=0.1)
    assert power["status"] == "within"


@pytest.mark.unit
def test_thin_history_is_not_judged():
    signals = build_signals(_run(0), _history(count=6), hr_model=_COEFFS)

    gct = _signal(signals, "gct")
    assert gct["status"] == "insufficient"
    assert gct["n"] == 6
    assert gct["reason_code"] == REASON_THIN_BASELINE
    assert gct["reason"] == "比べられる直近のランが 6 本で、判定には 10 本以上が必要"


# --------------------------------------------------------------------------- #
# Cardio signals
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_hr_vs_expected_uses_the_fitted_model():
    """140 bpm against a 136 bpm prediction sits at the centre of a +4 bpm band."""
    signals = build_signals(_run(0), _history(), hr_model=_COEFFS)

    hr = _signal(signals, "hr_vs_expected")
    assert hr["unit"] == "bpm"
    assert hr["today"] == pytest.approx(140.0)
    assert hr["expected"] == pytest.approx(136.0)
    assert hr["z"] == pytest.approx(0.0)
    assert hr["normal_low"] == pytest.approx(136.0, abs=0.1)
    assert hr["normal_high"] == pytest.approx(144.0, abs=0.1)


@pytest.mark.unit
def test_hr_vs_expected_flags_an_expensive_run():
    signals = build_signals(_run(0, avg_hr=145.0), _history(), hr_model=_COEFFS)

    hr = _signal(signals, "hr_vs_expected")
    assert hr["z"] == pytest.approx(2.5)
    assert hr["status"] == "outside"
    assert hr["adverse"] is True


@pytest.mark.unit
def test_hr_vs_expected_needs_a_model():
    signals = build_signals(_run(0), _history(), hr_model=None)

    hr = _signal(signals, "hr_vs_expected")
    assert hr["status"] == "insufficient"
    assert hr["reason_code"] == REASON_NO_HR_MODEL
    assert hr["reason"] == "同じ種類のランが少なく、想定心拍を計算できない"


@pytest.mark.unit
def test_drift_baseline_uses_same_intensity_family():
    """An interval session's drift must not widen the band judging an easy run."""
    easy_drifts = [3.0, 3.0, 4.0, 4.0, 4.0, 4.0, 5.0, 5.0, 5.0, 5.0, 6.0, 6.0]
    interval_drifts = [
        -15.0,
        -13.0,
        -11.0,
        -9.0,
        -7.0,
        -5.0,
        15.0,
        17.0,
        19.0,
        21.0,
        23.0,
        25.0,
    ]
    history = [
        _run(days_ago, hr_drift_percentage=drift)
        for days_ago, drift in enumerate(easy_drifts, start=1)
    ] + [
        _run(days_ago, hr_drift_percentage=drift, intensity_category="interval")
        for days_ago, drift in enumerate(interval_drifts, start=13)
    ]

    signals = build_signals(
        _run(0, hr_drift_percentage=11.0), history, hr_model=_COEFFS
    )

    drift = _signal(signals, "hr_drift")
    assert drift["n"] == len(easy_drifts)
    assert drift["status"] == "outside"
    assert drift["adverse"] is True

    # The same run judged against the mixed history would have passed unnoticed.
    mixed = compute_band(easy_drifts + interval_drifts, 11.0, higher_is_worse=True)
    assert mixed.status == "within"


@pytest.mark.unit
def test_drift_not_judged_in_heat():
    signals = build_signals(_run(0, temp=31.0), _history(), hr_model=_COEFFS)

    drift = _signal(signals, "hr_drift")
    assert drift["status"] == "insufficient"
    assert drift["reason_code"] == REASON_HOT
    assert drift["today"] == pytest.approx(4.0)


# --------------------------------------------------------------------------- #
# Reasons (#1278): the page prints ``reason`` verbatim, so every one is Japanese
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_every_reason_code_has_a_japanese_message():
    """A new REASON_* constant cannot ship without wording a reader can use."""
    codes = {
        value
        for name, value in vars(run_signals).items()
        if name.startswith("REASON_") and isinstance(value, str)
    }
    assert len(codes) == 10

    for code in codes:
        message = run_signals.describe_reason(code, _REASON_PARAMS.get(code))
        assert message, code
        assert message != code, f"{code} has no Japanese message"
        assert any(ord(char) > 127 for char in message), f"{code} reads as English"


@pytest.mark.unit
def test_thin_baseline_reason_is_japanese_with_counts():
    """The one a fresh history triggers: "baseline size 0 < 10" in Japanese."""
    signals = build_signals(_run(0), [], hr_model=_COEFFS)

    gct = _signal(signals, "gct")
    assert gct["reason"] == "比べられる直近のランが 0 本で、判定には 10 本以上が必要"
    assert gct["reason_code"] == "thin_baseline"


@pytest.mark.unit
def test_drift_in_heat_reason_mentions_temperature():
    signals = build_signals(_run(0, temp=31.0), _history(), hr_model=_COEFFS)

    drift = _signal(signals, "hr_drift")
    assert "31" in drift["reason"]
    assert "℃" in drift["reason"]


# --------------------------------------------------------------------------- #
# Streaks
# --------------------------------------------------------------------------- #


def _streak_history(most_recent: float) -> list[dict[str, Any]]:
    """A band of centre 0 / spread 1 whose last two runs lean the bad way."""
    baseline = [
        _run(days_ago, gct_delta_pct=_shaped(days_ago, 1.0))
        for days_ago in range(3, 33)
    ]
    return [
        *baseline,
        _run(2, gct_delta_pct=1.4),
        _run(1, gct_delta_pct=most_recent),
    ]


@pytest.mark.unit
def test_streak_counts_consecutive_adverse_runs():
    signals = build_signals(
        _run(0, gct_delta_pct=1.2), _streak_history(1.1), hr_model=_COEFFS
    )

    gct = _signal(signals, "gct")
    assert gct["z"] == pytest.approx(1.2)
    # 1.2 today, 1.1 yesterday, 1.4 the day before: a mild lean three runs long,
    # even though no single run is far enough out to be flagged on its own.
    assert gct["status"] == "within"
    assert gct["streak"] == 3


@pytest.mark.unit
def test_streak_breaks_on_a_normal_run():
    signals = build_signals(
        _run(0, gct_delta_pct=1.2), _streak_history(0.4), hr_model=_COEFFS
    )

    assert _signal(signals, "gct")["streak"] == 1


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_signals_are_json_serialisable():
    """DuckDB hands back numpy scalars and dates; the agent gets plain JSON."""
    today = _run(
        0,
        gct_delta_pct=np.float64(1.3),
        avg_hr=np.float32(141.0),
        n_valid_splits=np.int64(9),
        hr_drift_percentage=np.float64(5.2),
    )

    signals = build_signals(today, _history(), hr_model=_COEFFS)

    payload = json.dumps(signals, ensure_ascii=False)
    assert "NaN" not in payload
    for signal in signals:
        assert signal["status"] != "insufficient", signal["metric"]
        assert isinstance(signal["today"], float)
        assert isinstance(signal["z"], float)
        assert isinstance(signal["streak"], int)
