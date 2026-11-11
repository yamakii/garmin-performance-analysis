"""Unit tests for the phase-aware build baseline (Issue #1567)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from garmin_mcp.analysis.build_baseline import (
    classify_week,
    compute_build_baseline,
    window_composition,
)


def _mondays(first: str, n: int) -> list[str]:
    start = date.fromisoformat(first)
    return [(start + timedelta(days=7 * i)).isoformat() for i in range(n)]


def _block(
    phase: str, start: str, end: str, steps: list[tuple[str, str]] | None = None
) -> dict[str, Any]:
    return {
        "phase": phase,
        "start_date": start,
        "end_date": end,
        "long_run_ladder": [
            {"week_start": ws, "target_km": 20.0, "kind": kind}
            for ws, kind in (steps or [])
        ],
    }


# Nine Mondays: 5 build-block weeks (4th = cutback), then taper, race and two
# recovery weeks.
_WEEKS = _mondays("2026-08-03", 9)
_BLOCKS = [
    _block(
        "build",
        _WEEKS[0],
        "2026-09-06",
        [
            (_WEEKS[0], "build"),
            (_WEEKS[1], "build"),
            (_WEEKS[2], "hold"),
            (_WEEKS[3], "cutback"),
            (_WEEKS[4], "build"),
        ],
    ),
    _block(
        "taper", _WEEKS[5], "2026-09-20", [(_WEEKS[5], "taper"), (_WEEKS[6], "race")]
    ),
    _block("recovery", _WEEKS[7], "2026-10-04"),
]
_LOADS = [30.0, 40.0, 50.0, 20.0, 60.0, 10.0, 55.0, 15.0, 25.0]


def _weekly(weeks: list[str], loads: list[float]) -> list[dict[str, Any]]:
    return [
        {"week_start": w, "load_km": km} for w, km in zip(weeks, loads, strict=True)
    ]


@pytest.mark.unit
def test_classify_build_phase_build_step() -> None:
    blocks = [_block("build", "2026-09-07", "2026-09-27", [("2026-09-14", "build")])]
    assert classify_week("2026-09-14", blocks) == "build"


@pytest.mark.unit
def test_classify_build_phase_cutback_step() -> None:
    blocks = [_block("build", "2026-09-07", "2026-09-27", [("2026-09-14", "cutback")])]
    assert classify_week("2026-09-14", blocks) == "cutback"


@pytest.mark.unit
def test_classify_recovery_phase_build_step_is_not_build() -> None:
    blocks = [_block("recovery", "2026-09-07", "2026-09-27", [("2026-09-14", "build")])]
    assert classify_week("2026-09-14", blocks) == "recovery"


@pytest.mark.unit
def test_classify_uncovered_week() -> None:
    blocks = [_block("build", "2026-09-07", "2026-09-27")]
    assert classify_week("2026-01-05", blocks) == "unregistered"


@pytest.mark.unit
def test_baseline_excludes_deload_weeks() -> None:
    result = compute_build_baseline(_weekly(_WEEKS, _LOADS), _BLOCKS, 50.0)

    assert result["status"] == "ok"
    assert result["weekly_km"] == 45.0
    assert result["ratio"] == pytest.approx(1.11, abs=0.01)
    assert result["weeks_used"] == [_WEEKS[0], _WEEKS[1], _WEEKS[2], _WEEKS[4]]
    assert result["note_ja"] is None


@pytest.mark.unit
def test_baseline_no_blocks() -> None:
    result = compute_build_baseline(_weekly(_WEEKS, _LOADS), [], 50.0)

    assert result["status"] == "no_blocks"
    assert result["weekly_km"] is None
    assert result["ratio"] is None
    assert result["note_ja"]


@pytest.mark.unit
def test_baseline_one_build_week_insufficient() -> None:
    weeks = _mondays("2026-09-07", 3)
    blocks = [
        _block("build", weeks[0], "2026-09-13", [(weeks[0], "build")]),
        _block("recovery", weeks[1], "2026-09-27"),
    ]

    result = compute_build_baseline(_weekly(weeks, [40.0, 10.0, 12.0]), blocks, 12.0)

    assert result["status"] == "insufficient"
    assert result["weekly_km"] is None
    assert result["weeks_used"] == [weeks[0]]
    assert result["note_ja"]


@pytest.mark.unit
def test_baseline_takes_most_recent_eight() -> None:
    weeks = _mondays("2026-06-01", 10)
    blocks = [_block("build", weeks[0], "2026-08-09")]
    loads = [float(km) for km in range(10, 101, 10)]

    result = compute_build_baseline(_weekly(weeks, loads), blocks, 65.0)

    assert result["status"] == "ok"
    assert result["weekly_km"] == 65.0
    assert result["weeks_used"] == weeks[2:]
    assert result["ratio"] == pytest.approx(1.0)


@pytest.mark.unit
def test_window_composition_labels_each_week() -> None:
    rows = window_composition(_weekly(_WEEKS, _LOADS), _BLOCKS)

    assert [row["kind"] for row in rows] == ["taper", "race", "recovery", "recovery"]
    assert [row["week_start"] for row in rows] == _WEEKS[5:]
    assert [row["load_km"] for row in rows] == [10.0, 55.0, 15.0, 25.0]
