"""Grounding of the athlete's stated context in the run note (#1522).

``context.athlete_context`` is what the athlete said about the run (a load,
a commute, carried-over strides). It may explain an adverse signal but -- like
every ``context.*`` key -- is never a growth point. The allow-list also names
the keys the run-note CONTEXT actually emits (``prescription_for_run``, not the
stale ``prescription`` / ``ladder_step``).

Split from ``test_run_note_grounding.py`` to keep it under the test-file size
budget; the payload helpers are shared from there.
"""

from __future__ import annotations

import pytest

from garmin_mcp.scripts.prefetch_activity_context import build_run_note_context
from garmin_mcp.validation.validators import (
    CONTEXT_EVIDENCE_KEYS,
    check_run_note_grounding,
)
from tests.validation.test_run_note_grounding import (
    _adverse,
    _growth_on,
    _note_data,
    _report,
)


@pytest.mark.unit
def test_grounding_accepts_context_athlete_context_for_note():
    """A stated load may explain an adverse cadence outlier.

    Notes carry a signal name, not an evidence key, so the stated
    circumstance is cited where the note's cue is carried over.
    """
    report = _report(signals=_adverse("cadence"))
    data = _note_data(
        good_points=[],
        notes=[
            {
                "signal": "cadence",
                "text": (
                    "3 kg の荷物を背負った帰宅ランで、"
                    "歩幅とピッチが抑えられた影響と見られます。"
                ),
            }
        ],
        next_challenge_evidence="context.athlete_context",
    )

    assert check_run_note_grounding(data, report) == (True, None)


@pytest.mark.unit
def test_grounding_rejects_athlete_context_as_growth_point():
    """A stated circumstance explains a signal; it is never the weakness."""
    ok, reason = check_run_note_grounding(
        _growth_on("context.athlete_context"), _report()
    )

    assert ok is False
    assert reason is not None
    assert "context.athlete_context" in reason
    assert "background" in reason


@pytest.mark.unit
def test_grounding_accepts_prescription_for_run_key():
    """The allow-list names the key the CONTEXT emits, not a stale alias."""
    allowed = _note_data(
        good_points=[
            {
                "text": "処方の狙いどおりの走りになっています。",
                "evidence": "context.prescription_for_run",
            }
        ]
    )
    assert check_run_note_grounding(allowed, _report()) == (True, None)

    stale = _note_data(
        good_points=[
            {
                "text": "ロングの段階どおりに距離を踏めています。",
                "evidence": "context.ladder_step",
            }
        ]
    )
    ok, reason = check_run_note_grounding(stale, _report())
    assert ok is False
    assert reason is not None
    assert "context.ladder_step" in reason


@pytest.mark.unit
def test_context_evidence_keys_are_emitted_by_the_run_note_context():
    """Every allowed context key is a key the run-note CONTEXT carries."""
    context = build_run_note_context({"activity_id": 1})

    assert context is not None
    assert set(context) >= CONTEXT_EVIDENCE_KEYS
