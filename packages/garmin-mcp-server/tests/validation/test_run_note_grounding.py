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
        "next_challenge": "心拍を先に見て、上限の150を超えないペースで走り続けましょう。",
        "timeline": [{"moment_id": "m3", "text": "終始落ち着いたペースで進みました。"}],
        "notes": [],
    }
    data.update(overrides)
    # The carried-over point is one of the note's own points (#1358): unless a
    # test sets it, it follows whichever point the test put in.
    if "next_challenge_evidence" not in overrides:
        points = [*data["good_points"], *data["growth_points"]]
        data["next_challenge_evidence"] = (
            points[0]["evidence"] if points else "plan.hr_ceiling"
        )
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


# --- good points (#1329) ---------------------------------------------------


def _good_on(evidence: str, **overrides: Any) -> dict[str, Any]:
    """A run_note whose one good point rests on ``evidence``."""
    return _note_data(
        good_points=[{"text": "よく走れています。", "evidence": evidence}], **overrides
    )


@pytest.mark.unit
def test_good_point_rejects_within_signal():
    """A within-range value is not a strength (never_write #4)."""
    ok, reason = check_run_note_grounding(_good_on("signals.gct"), _report())

    assert ok is False
    assert reason is not None
    assert "signals.gct" in reason


@pytest.mark.unit
def test_good_point_accepts_favorable_outlier():
    """A signal outside its range on the favourable side is a strength."""
    report = _report(
        signals=[{"metric": "hr_drift", "status": "outside", "adverse": False}]
    )

    assert check_run_note_grounding(_good_on("signals.hr_drift"), report) == (
        True,
        None,
    )


@pytest.mark.unit
def test_good_point_rejects_acceptable_moment():
    """A walk the purpose allows is not something to praise."""
    data = _good_on(
        "moments.m2", timeline=[{"moment_id": "m3", "text": "落ち着いて進みました。"}]
    )

    ok, reason = check_run_note_grounding(data, _report_with_m2("acceptable"))

    assert ok is False
    assert reason is not None
    assert "acceptable" in reason


@pytest.mark.unit
def test_good_point_rejects_moment_narrated_in_timeline():
    """A scene the timeline tells is said once, in the timeline (never_write #5)."""
    data = _good_on(
        "moments.m2", timeline=[{"moment_id": "m2", "text": "終盤に上げました。"}]
    )

    ok, reason = check_run_note_grounding(data, _report_with_m2("neutral"))

    assert ok is False
    assert reason is not None
    assert "timeline" in reason


@pytest.mark.unit
def test_good_point_accepts_neutral_moment_not_in_timeline():
    """A neutral scene the timeline leaves out may carry a strength."""
    data = _good_on(
        "moments.m2", timeline=[{"moment_id": "m3", "text": "落ち着いて進みました。"}]
    )

    assert check_run_note_grounding(data, _report_with_m2("neutral")) == (True, None)


@pytest.mark.unit
def test_good_point_rejects_off_plan_axis():
    """An axis that came out off plan is not a strength."""
    ok, reason = check_run_note_grounding(_good_on("plan.volume"), _report())

    assert ok is False
    assert reason is not None
    assert "plan.volume" in reason


@pytest.mark.unit
def test_good_points_may_be_empty():
    """With nothing legitimately strong, good_points is left empty."""
    assert check_run_note_grounding(_note_data(good_points=[]), _report()) == (
        True,
        None,
    )


@pytest.mark.unit
def test_minimal_run_note_passes_without_good_points():
    """No plan, every signal within range, no previous run: an empty list passes.

    The E2E review asked whether such a run can still produce a valid note once
    scenes and within-range values stop counting as strengths (#1329).
    """
    report = _report(
        plan=None,
        signals=[{"metric": "gct", "status": "within", "adverse": False}],
        vs_previous=None,
        recurrence=[],
    )
    # With no point to carry, the cue rests on a key the report carries -- here
    # the steady scene the timeline tells (#1358).
    data = _note_data(good_points=[], next_challenge_evidence="moments.m3")

    assert check_run_note_grounding(data, report) == (True, None)


def _ceiling_report(pct_over: float | None) -> dict[str, Any]:
    """A report whose hr_ceiling axis is on plan (by average HR)."""
    plan: dict[str, Any] = {"checks": [{"axis": "hr_ceiling", "on_plan": True}]}
    if pct_over is not None:
        plan["hr_ceiling"] = {"bpm": 150, "seconds_over": 0.0, "pct_over": pct_over}
    return _report(plan=plan)


@pytest.mark.unit
def test_good_point_rejects_hr_ceiling_when_much_over():
    """30 minutes above the ceiling is not kept, whatever the average (#1332)."""
    ok, reason = check_run_note_grounding(
        _good_on("plan.hr_ceiling"), _ceiling_report(14.9)
    )

    assert ok is False
    assert reason is not None
    assert "14.9%" in reason


@pytest.mark.unit
def test_good_point_accepts_hr_ceiling_when_briefly_over():
    """A 21 s overshoot (1.2%) still lets the note credit the ceiling."""
    assert check_run_note_grounding(
        _good_on("plan.hr_ceiling"), _ceiling_report(1.2)
    ) == (True, None)


@pytest.mark.unit
def test_good_point_accepts_hr_ceiling_without_share():
    """Without a judged share (no ceiling block) the on-plan axis stands."""
    assert check_run_note_grounding(
        _good_on("plan.hr_ceiling"), _ceiling_report(None)
    ) == (True, None)


def _breakdown_report() -> dict[str, Any]:
    """A prescribed run that came apart: continuity off plan + a breakdown scene."""
    return _report(
        plan={
            "checks": [
                {"axis": "hr_ceiling", "on_plan": True},
                {"axis": "continuity", "on_plan": False},
            ]
        },
        moments=[
            {"id": "m1", "label": "start"},
            {
                "id": "m2",
                "kind": "breakdown",
                "policy": {"verdict": "concern", "reason": "test"},
            },
            {"id": "m3", "label": "steady"},
        ],
    )


@pytest.mark.unit
def test_growth_points_reject_continuity_and_breakdown_together():
    """One collapse is one growth point, not two (#1353)."""
    data = _note_data(
        growth_points=[
            {
                "text": "最後まで走り続けることが、次のロングの課題です。",
                "evidence": "plan.continuity",
            },
            {
                "text": "18 km からの崩れを防ぎたいところです。",
                "evidence": "moments.m2",
            },
        ]
    )

    ok, reason = check_run_note_grounding(data, _breakdown_report())

    assert ok is False
    assert reason is not None
    assert "same collapse" in reason
    assert "plan.continuity" in reason


@pytest.mark.unit
def test_growth_point_on_continuity_alone_passes():
    """The off-plan continuity axis alone carries the collapse (#1353)."""
    data = _note_data(
        growth_points=[
            {
                "text": "最後まで走り続けることが、次のロングの課題です。",
                "evidence": "plan.continuity",
            }
        ]
    )

    assert check_run_note_grounding(data, _breakdown_report()) == (True, None)


@pytest.mark.unit
def test_next_challenge_evidence_must_match_a_point():
    """A carried-over cue with no point of today's behind it is rejected (#1358)."""
    data = _note_data(next_challenge_evidence="signals.gct")

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "next_challenge_evidence" in reason
    assert "signals.gct" in reason


@pytest.mark.unit
def test_next_challenge_evidence_matching_growth_point_passes():
    """Carrying over the growth point is the normal case (#1358)."""
    data = _note_data(
        growth_points=[
            {
                "text": "距離が処方に届かず、量の目標に少し足りませんでした。",
                "evidence": "plan.volume",
            }
        ],
        next_challenge_evidence="plan.volume",
    )

    assert check_run_note_grounding(data, _report()) == (True, None)


@pytest.mark.unit
def test_next_challenge_evidence_without_points_must_resolve():
    """With no point at all, the carried key must still exist in the report."""
    data = _note_data(good_points=[], next_challenge_evidence="signals.nope")

    ok, reason = check_run_note_grounding(data, _report())

    assert ok is False
    assert reason is not None
    assert "next_challenge_evidence" in reason


# --- structure-derived plan axes (#1406) ------------------------------------


def _structured_report() -> dict[str, Any]:
    """Two band steps judged separately, plus one axis that was not judged."""
    return _report(
        plan={
            "checks": [
                {"axis": "intensity", "status": "on_plan", "on_plan": True},
                {"axis": "hr_band", "status": "on_plan", "on_plan": True},
                {"axis": "hr_band_2", "status": "off_plan", "on_plan": False},
                {"axis": "pace_band", "status": "insufficient", "on_plan": False},
            ]
        }
    )


@pytest.mark.unit
def test_evidence_resolves_plan_hr_band_2():
    """Every axis id in plan.checks is an evidence key, numbered ones included."""
    data = _note_data(
        good_points=[
            {"text": "一本目の心拍帯は狙いどおりでした。", "evidence": "plan.hr_band"}
        ],
        growth_points=[
            {
                "text": "二本目は心拍帯を外れる時間が長めでした。",
                "evidence": "plan.hr_band_2",
            }
        ],
        next_challenge_evidence="plan.hr_band_2",
    )

    assert check_run_note_grounding(data, _structured_report()) == (True, None)


@pytest.mark.unit
def test_growth_point_rejected_on_insufficient_axis():
    """An axis that was not judged is not a weakness."""
    data = _note_data(
        good_points=[],
        growth_points=[
            {
                "text": "ペース帯に収まっていませんでした。",
                "evidence": "plan.pace_band",
            }
        ],
        next_challenge_evidence="plan.pace_band",
    )

    ok, reason = check_run_note_grounding(data, _structured_report())

    assert ok is False
    assert reason is not None
    assert "plan.pace_band" in reason
    assert "insufficient" in reason
