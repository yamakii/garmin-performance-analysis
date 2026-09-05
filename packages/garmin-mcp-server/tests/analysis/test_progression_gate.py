"""Unit tests for the deterministic long-run progression gate (#982).

Every case feeds ``compute_long_run_progression_gate`` two plain dicts (a
current run and, optionally, a reference run) -- no DB, no I/O.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.progression_gate import (
    build_long_run_progression_gate,
    compute_long_run_progression_gate,
)


def _run(
    activity_id: int = 9001,
    *,
    gct_fade_ms: float | None = None,
    cadence_fade_spm: float | None = None,
    pace_fade_pct: float | None = None,
    temperature_c: float | None = None,
) -> dict[str, Any]:
    """Build a durability-shaped dict with just the gate-relevant fields."""
    return {
        "activity_id": activity_id,
        "gct_fade_ms": gct_fade_ms,
        "cadence_fade_spm": cadence_fade_spm,
        "pace_fade_pct": pace_fade_pct,
        "temperature_c": temperature_c,
    }


@pytest.mark.unit
def test_gate_green_when_no_trigger() -> None:
    """Every metric inside its threshold -> green / extend, nothing triggered."""
    current = _run(gct_fade_ms=4.0, cadence_fade_spm=-2.0, pace_fade_pct=3.0)
    reference = _run(8001, gct_fade_ms=6.0)

    gate = compute_long_run_progression_gate(current, reference)

    assert gate["verdict"] == "green"
    assert gate["recommendation"] == "extend"
    assert gate["triggers"] == []
    assert all(t["worse_than_reference"] is False for t in gate["triggers"])
    assert gate["reference_activity_id"] == 8001
    assert gate["decoupling_contaminated"] is False
    assert "延長" in gate["reason_ja"]


@pytest.mark.unit
def test_gate_red_when_gct_trigger_and_worse_than_reference() -> None:
    """GCT +14 ms vs a reference at +3 ms -> clearly worse -> red / shorten."""
    current = _run(gct_fade_ms=14.0, cadence_fade_spm=-1.0, pace_fade_pct=2.0)
    reference = _run(8002, gct_fade_ms=3.0)

    gate = compute_long_run_progression_gate(current, reference)

    assert gate["verdict"] == "red"
    assert gate["recommendation"] == "shorten"
    assert [t["metric"] for t in gate["triggers"]] == ["gct_fade_ms"]
    trigger = gate["triggers"][0]
    assert trigger["current"] == 14.0
    assert trigger["reference"] == 3.0
    assert trigger["threshold"] == 10.0
    assert trigger["worse_than_reference"] is True


@pytest.mark.unit
def test_gate_yellow_when_trigger_but_not_worse_than_reference() -> None:
    """GCT +12 ms against a reference at +11 ms is noise, not a regression."""
    current = _run(gct_fade_ms=12.0, cadence_fade_spm=-1.0, pace_fade_pct=2.0)
    reference = _run(8003, gct_fade_ms=11.0)

    gate = compute_long_run_progression_gate(current, reference)

    assert gate["verdict"] == "yellow"
    assert gate["recommendation"] == "repeat"
    assert gate["triggers"][0]["worse_than_reference"] is False


@pytest.mark.unit
def test_gate_red_without_reference_when_cadence_trigger() -> None:
    """A fired trigger with nothing to compare against cannot be exonerated."""
    current = _run(gct_fade_ms=2.0, cadence_fade_spm=-6.0, pace_fade_pct=1.0)

    gate = compute_long_run_progression_gate(current, None)

    assert gate["verdict"] == "red"
    assert gate["recommendation"] == "shorten"
    assert [t["metric"] for t in gate["triggers"]] == ["cadence_fade_spm"]
    assert gate["triggers"][0]["reference"] is None
    assert gate["reference_activity_id"] is None


@pytest.mark.unit
def test_gate_yellow_hot_run_without_reference() -> None:
    """32 C with no reference: nothing fired, but the read is unreliable."""
    current = _run(
        gct_fade_ms=3.0,
        cadence_fade_spm=-1.0,
        pace_fade_pct=4.0,
        temperature_c=32.0,
    )

    gate = compute_long_run_progression_gate(current, None)

    assert gate["verdict"] == "yellow"
    assert gate["recommendation"] == "repeat"
    assert gate["decoupling_contaminated"] is True
    assert gate["triggers"] == []


@pytest.mark.unit
def test_gate_insufficient_data_without_halves() -> None:
    """No half-split metrics at all -> nothing to judge."""
    gate = compute_long_run_progression_gate(_run(), None)

    assert gate["verdict"] == "insufficient_data"
    assert gate["recommendation"] == "repeat"
    assert gate["triggers"] == []


@pytest.mark.unit
def test_gate_green_when_hot_but_reference_exists() -> None:
    """Heat alone does not downgrade a run that has a comparable reference."""
    current = _run(
        gct_fade_ms=3.0,
        cadence_fade_spm=-1.0,
        pace_fade_pct=4.0,
        temperature_c=31.0,
    )
    reference = _run(8004, gct_fade_ms=4.0, temperature_c=30.5)

    gate = compute_long_run_progression_gate(current, reference)

    assert gate["verdict"] == "green"
    assert gate["decoupling_contaminated"] is True


@pytest.mark.unit
def test_build_long_run_progression_gate_wraps_reader() -> None:
    """The shared builder returns both runs alongside the verdict."""

    class _Source:
        def get_activity_durability(self, activity_id: int) -> dict[str, Any]:
            return _run(activity_id, gct_fade_ms=4.0, cadence_fade_spm=-1.0)

        def find_reference_long_run(self, activity_id: int) -> dict[str, Any]:
            return _run(8005, gct_fade_ms=5.0)

    payload = build_long_run_progression_gate(_Source(), 7777)

    assert payload["activity_id"] == 7777
    assert payload["current"]["activity_id"] == 7777
    assert payload["reference"]["activity_id"] == 8005
    assert payload["verdict"] == "green"
    assert payload["reference_activity_id"] == 8005
