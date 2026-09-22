"""Did the run deliver what its purpose asked for? (Issue #1340).

The cases that matter are the ones a walking threshold would get wrong: a run
that came apart without ever walking, and a run that lost two kilometres and
then found the pace again.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from garmin_mcp.analysis.purpose_outcome import evaluate

pytestmark = pytest.mark.unit


def _splits(
    paces: Sequence[float], *, cadence: float = 178.0, distance_km: float = 1.0
) -> list[dict[str, Any]]:
    """One row per kilometre at the given paces."""
    return [
        {
            "split_index": i,
            "distance_km": distance_km,
            "pace_s_per_km": pace,
            "cadence": cadence,
        }
        for i, pace in enumerate(paces, start=1)
    ]


def test_outcome_met_when_pace_holds() -> None:
    """Ten kilometres around one pace: the run did what it was for."""
    outcome = evaluate(
        "long_easy", _splits([420, 425, 418, 430, 422, 415, 428, 420, 424, 419])
    )

    assert outcome is not None
    assert outcome.met is True
    assert outcome.sustained_share == 1.0
    assert outcome.breakdown_from_km is None


def test_outcome_breakdown_when_last_third_collapses() -> None:
    """Six kilometres held, then four the athlete could not hold at all."""
    outcome = evaluate("long_easy", _splits([420] * 6 + [700] * 4))

    assert outcome is not None
    assert outcome.met is False
    assert outcome.breakdown_from_km == 6.0
    assert outcome.sustained_share == 0.6


def test_outcome_ignores_temporary_dip() -> None:
    """Two slow kilometres the athlete came back from are a dip, not a collapse."""
    outcome = evaluate("long_easy", _splits([420] * 4 + [700, 700] + [420] * 4))

    assert outcome is not None
    assert outcome.met is True
    assert outcome.breakdown_from_km is None


def test_outcome_breakdown_without_walking() -> None:
    """The collapse is judged on the effort, not on whether the athlete walked."""
    running = _splits([420] * 6, cadence=178.0)
    slow_but_running = _splits([640] * 4, cadence=176.0)
    for index, row in enumerate(slow_but_running, start=7):
        row["split_index"] = index

    outcome = evaluate("long_easy", running + slow_but_running)

    assert outcome is not None
    assert outcome.met is False
    assert outcome.breakdown_from_km == 6.0


def test_outcome_none_for_interval_purpose() -> None:
    """Intervals are judged on their reps, not on holding one pace."""
    assert evaluate("intervals", _splits([300, 500, 300, 500, 300])) is None


def test_outcome_sustained_pace_excludes_breakdown() -> None:
    """The pace this run held is the pace of the part it held (#1341)."""
    outcome = evaluate("long_easy", _splits([420] * 6 + [700] * 4))

    assert outcome is not None
    assert outcome.sustained_pace_s_per_km == 420.0


def test_outcome_needs_splits() -> None:
    """A run with no judgeable kilometre has no outcome."""
    assert evaluate("long_easy", []) is None
