"""Tests for ``check_run_note_grounding`` (Epic #1247, Issue #1251).

The coach review is the only LLM-written part of the single-run page, so every
claim in it must resolve against the deterministic run report the page renders.
These tests pin the two failure modes the guard exists for: a weakness built on
a signal that never left its normal range (or an axis that came out on plan),
and a scene or key that the report does not contain.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.validation.validators import (
    CONTEXT_EVIDENCE_KEYS,
    check_run_note_grounding,
)


def _report(**overrides: Any) -> dict[str, Any]:
    """A report with no adverse outlier: gct within, vo edge, cadence favourable."""
    report: dict[str, Any] = {
        "plan": {
            "checks": [
                {"axis": "hr_ceiling", "on_plan": True},
                {"axis": "volume", "on_plan": False},
            ]
        },
        "signals": [
            {"metric": "gct", "status": "within", "adverse": False},
            {"metric": "vo", "status": "edge", "adverse": True},
            {"metric": "cadence", "status": "outside", "adverse": False},
        ],
        "moments": [
            {"id": "m1", "label": "start"},
            {"id": "m2", "label": "climb"},
            {"id": "m3", "label": "steady"},
            {"id": "m4", "label": "finish"},
        ],
        "recurrence": [{"kind": "hr_drift"}],
        "vs_previous": {"pace_delta_sec": -4.0},
        "conditions": {"temp_celsius": 21.0},
    }
    report.update(overrides)
    return report


def _note_data(**overrides: Any) -> dict[str, Any]:
    """A minimal grounded run_note payload (one good point, no growth point)."""
    data: dict[str, Any] = {
        "story": "週の位置づけどおりの有酸素走で、狙った役割をきちんと果たしました。",
        "good_points": [
            {
                "text": "心拍を上限の内側で収めて走り切れています。",
                "evidence": "plan.hr_ceiling",
            }
        ],
        "growth_points": [],
        "next_challenge": "次回も150bpmを超えないように、140bpm前後で落ち着かせましょう。",
        "timeline": [{"moment_id": "m3", "text": "終始落ち着いたペースで進みました。"}],
        "notes": [],
    }
    data.update(overrides)
    return data


@pytest.mark.unit
def test_growth_point_on_within_signal_is_rejected():
    """A signal inside its normal range is not a weakness."""
    data = _note_data(
        growth_points=[
            {
                "text": "接地時間をもう少し短くしたいところです。",
                "evidence": "signals.gct",
            }
        ]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "signals.gct" in reason


@pytest.mark.unit
def test_growth_point_on_edge_signal_is_rejected():
    """``edge`` is still inside the normal band."""
    data = _note_data(
        growth_points=[
            {
                "text": "上下動をもう少し抑えられると楽になります。",
                "evidence": "signals.vo",
            }
        ]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "signals.vo" in reason


@pytest.mark.unit
def test_growth_point_on_outside_adverse_signal_is_accepted():
    """An outside + adverse signal is a legitimate growth point (with its note)."""
    report = _report(
        signals=[
            {"metric": "gct", "status": "outside", "adverse": True},
            {"metric": "vo", "status": "within", "adverse": False},
        ]
    )
    data = _note_data(
        growth_points=[
            {"text": "接地時間が普段より長めに出ています。", "evidence": "signals.gct"}
        ],
        notes=[
            {
                "signal": "gct",
                "text": "終盤の上り区間で接地が伸びた影響が大きそうです。",
            }
        ],
    )

    assert check_run_note_grounding(data, report) == (True, None)


@pytest.mark.unit
def test_growth_point_on_favourable_outlier_is_rejected():
    """An outlier in the good direction is a strength, never a growth point."""
    data = _note_data(
        growth_points=[
            {
                "text": "ケイデンスをもう少し上げたいところです。",
                "evidence": "signals.cadence",
            }
        ]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "signals.cadence" in reason


@pytest.mark.unit
def test_growth_point_on_plan_axis_is_rejected():
    """An axis that came out on plan is not an improvement area."""
    data = _note_data(
        growth_points=[
            {
                "text": "心拍の上限管理をもう少し丁寧にしたいです。",
                "evidence": "plan.hr_ceiling",
            }
        ]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "plan.hr_ceiling" in reason


def _report_with_m2(verdict: str) -> dict[str, Any]:
    """The default report with ``m2`` judged ``verdict`` by the purpose policy."""
    return _report(
        moments=[
            {"id": "m1", "label": "start"},
            {
                "id": "m2",
                "kind": "walk_break",
                "policy": {"verdict": verdict, "reason": "test"},
            },
            {"id": "m3", "label": "steady"},
        ]
    )


def _growth_on(evidence: str) -> dict[str, Any]:
    """A run_note whose one growth point rests on ``evidence``."""
    return _note_data(
        growth_points=[
            {
                "text": "途中の歩きを減らせると目標ペースの確認になります。",
                "evidence": evidence,
            }
        ]
    )


@pytest.mark.unit
def test_growth_point_rejects_non_concern_moment():
    """A scene the purpose accepts (a walk on an aerobic long run) is no weakness."""
    ok, reason = check_run_note_grounding(
        _growth_on("moments.m2"), _report_with_m2("acceptable")
    )

    assert ok is False
    assert reason is not None
    assert "moments.m2" in reason
    assert "acceptable" in reason


@pytest.mark.unit
def test_growth_point_accepts_concern_moment():
    """A scene the purpose judges a concern may carry a growth point."""
    assert check_run_note_grounding(
        _growth_on("moments.m2"), _report_with_m2("concern")
    ) == (True, None)


@pytest.mark.unit
def test_growth_point_rejects_recurrence_evidence():
    """A recurrence is background for a weakness, never the weakness itself."""
    report = _report(recurrence=[{"kind": "fade"}])

    ok, reason = check_run_note_grounding(_growth_on("recurrence.fade"), report)

    assert ok is False
    assert reason is not None
    assert "recurrence.fade" in reason


@pytest.mark.unit
def test_unknown_evidence_key_is_rejected():
    """A signal the report does not carry cannot support a claim."""
    data = _note_data(
        good_points=[
            {"text": "未知の指標がとても良い値でした。", "evidence": "signals.unknown"}
        ]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "signals.unknown" in reason


@pytest.mark.unit
def test_context_evidence_uses_allow_list():
    """``context.<field>`` resolves against the fixed allow-list, not the report."""
    assert "week_position" in CONTEXT_EVIDENCE_KEYS

    allowed = _note_data(
        good_points=[
            {
                "text": "週の狙いどおりの位置づけで走れています。",
                "evidence": "context.week_position",
            }
        ]
    )
    assert check_run_note_grounding(allowed, _report()) == (True, None)

    invented = _note_data(
        good_points=[
            {
                "text": "何かよく分からない根拠に基づく良い点です。",
                "evidence": "context.anything_else",
            }
        ]
    )
    ok, reason = check_run_note_grounding(invented, _report())
    assert ok is False
    assert reason is not None
    assert "context.anything_else" in reason


@pytest.mark.unit
def test_plan_evidence_rejected_without_plan():
    """An unprescribed run has no plan axis to cite."""
    data = _note_data(
        good_points=[
            {"text": "計画どおりの距離を踏めています。", "evidence": "plan.volume"}
        ]
    )

    ok, reason = check_run_note_grounding(data, _report(plan=None))

    assert ok is False
    assert reason is not None
    assert "plan.volume" in reason


@pytest.mark.unit
def test_timeline_with_unknown_moment_id_is_rejected():
    """A timeline item must name a scene the report contains."""
    data = _note_data(
        timeline=[{"moment_id": "m9", "text": "存在しない場面を語っています。"}]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "m9" in reason


@pytest.mark.unit
def test_adverse_signal_without_note_is_rejected():
    """An adverse outlier must be explained, not passed over in silence."""
    report = _report(
        signals=[{"metric": "gct", "status": "outside", "adverse": True}],
    )
    data = _note_data(notes=[])

    ok, reason = check_run_note_grounding(data, report)

    assert ok is False
    assert reason is not None
    assert "gct" in reason


@pytest.mark.unit
def test_note_on_within_signal_is_rejected():
    """Notes exist only for adverse outliers, not for normal values."""
    data = _note_data(
        notes=[{"signal": "vo", "text": "上下動はいつもどおりの範囲に収まっています。"}]
    )

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "vo" in reason


@pytest.mark.unit
def test_empty_growth_points_is_valid():
    """A clean run needs no growth point at all."""
    assert check_run_note_grounding(_note_data(), _report()) == (True, None)
