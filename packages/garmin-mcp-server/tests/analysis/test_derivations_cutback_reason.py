"""The long-run cutback gate states why it applies now (Issue #1524)."""

import pytest

from garmin_mcp.analysis.derivations import (
    LONG_RUN_CUTBACK_TRIGGER_WEEKS,
    _cutback_reason_ja,
    compute_trend_headline_metrics,
    long_run_extension_weeks,
)

_THREE_EXTENSIONS = [
    {"week_start": "2026-10-25", "longest_run_sec": 5760, "longest_run_km": 16},
    {"week_start": "2026-11-01", "longest_run_sec": 7920, "longest_run_km": 22},
    {"week_start": "2026-11-08", "longest_run_sec": 10080, "longest_run_km": 28},
]


@pytest.mark.unit
def test_cutback_reason_lists_counted_weeks():
    reason = _cutback_reason_ja(_THREE_EXTENSIONS, LONG_RUN_CUTBACK_TRIGGER_WEEKS)

    assert reason is not None
    for label in ("10/25", "11/1", "11/8"):
        assert label in reason
    for distance in ("16 km", "22 km", "28 km"):
        assert distance in reason
    assert f"{LONG_RUN_CUTBACK_TRIGGER_WEEKS} 週続くと" in reason
    # Why the cycle matters, and the condition that cancels it.
    assert "腱・骨" in reason
    assert "75% 未満" in reason


@pytest.mark.unit
def test_cutback_reason_none_when_not_due():
    assert (
        _cutback_reason_ja(_THREE_EXTENSIONS[1:], LONG_RUN_CUTBACK_TRIGGER_WEEKS)
        is None
    )


@pytest.mark.unit
def test_long_run_extension_weeks_names_only_counted_weeks():
    """A hold is skipped and a reset week ends the walk, as in the counter."""
    weeks = [
        {"week_start": "2026-10-11", "longest_run_sec": 9000},
        {"week_start": "2026-10-18", "longest_run_sec": 3000},  # reset
        {"week_start": "2026-10-25", "longest_run_sec": 5760},  # extension
        {"week_start": "2026-11-01", "longest_run_sec": 5800},  # hold
        {"week_start": "2026-11-08", "longest_run_sec": 7000},  # extension
    ]

    counted = long_run_extension_weeks(weeks)

    assert [w["week_start"] for w in counted] == ["2026-10-25", "2026-11-08"]


@pytest.mark.unit
def test_headline_metrics_carry_cutback_reason():
    weeks = [
        {"week_start": "2026-10-18", "load_km": 30, "longest_run_sec": 4800},
        {"week_start": "2026-10-25", "load_km": 32, "longest_run_sec": 5760},
        {"week_start": "2026-11-01", "load_km": 35, "longest_run_sec": 7920},
        {"week_start": "2026-11-08", "load_km": 38, "longest_run_sec": 10080},
    ]

    due = compute_trend_headline_metrics({"load_trend": {"weeks": weeks}})
    not_due = compute_trend_headline_metrics({"load_trend": {"weeks": weeks[:3]}})

    assert due["cutback_due_long_run"] is True
    assert "11/8" in due["cutback_reason_ja"]
    assert "168 分" in due["cutback_reason_ja"]
    assert not_due["cutback_due_long_run"] is False
    assert not_due["cutback_reason_ja"] is None
