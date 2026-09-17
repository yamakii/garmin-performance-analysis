"""Unit tests for the deterministic symptom rule (#1223).

Every case is built from plain row dicts (no DB), mirroring what
``AthleteReader.get_symptoms`` returns for the rule's 14-day window.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from garmin_mcp.analysis.symptoms import evaluate_symptom_rule

_TODAY = date(2026, 9, 18)


def _day(offset: int) -> str:
    """``offset`` days before the reference day, as ``YYYY-MM-DD``."""
    return str(_TODAY - timedelta(days=offset))


def _row(
    days_ago: int,
    severity: int,
    body_region: str = "calf",
    side: str | None = "right",
) -> dict[str, Any]:
    """One symptom row ``days_ago`` before the reference day."""
    return {
        "date": _day(days_ago),
        "body_region": body_region,
        "side": side,
        "severity": severity,
        "phase": "morning",
    }


@pytest.mark.unit
def test_consecutive_two_reports_ge_3_flags() -> None:
    """Right calf 4 (d-2) then 3 (d): two reports at 3+ flag the region."""
    result = evaluate_symptom_rule([_row(2, 4), _row(0, 3)], str(_TODAY))

    assert result["flag"] is True
    assert len(result["flagged_regions"]) == 1
    region = result["flagged_regions"][0]
    assert region["body_region"] == "calf"
    assert region["side"] == "right"
    assert region["rule"] == "consecutive"
    assert region["latest_severity"] == 3
    assert region["latest_date"] == str(_TODAY)
    assert region["reports"] == [
        {"date": _day(2), "severity": 4},
        {"date": _day(0), "severity": 3},
    ]
    assert "右ふくらはぎ" in result["reason_ja"]
    assert "2回連続で3以上" in result["reason_ja"]
    assert result["days_since_last_report"] == 0


@pytest.mark.unit
def test_single_report_ge_3_does_not_flag() -> None:
    """One right-calf 4 is a niggle, not a pattern: no flag."""
    result = evaluate_symptom_rule([_row(1, 4)], str(_TODAY))

    assert result["flag"] is False
    assert result["flagged_regions"] == []
    assert result["days_since_last_report"] == 1


@pytest.mark.unit
def test_acute_ge_5_flags_immediately() -> None:
    """Left shin 6 yesterday flags on its own (acute rule)."""
    result = evaluate_symptom_rule(
        [_row(1, 6, body_region="shin", side="left")], str(_TODAY)
    )

    assert result["flag"] is True
    region = result["flagged_regions"][0]
    assert region["rule"] == "acute"
    assert region["body_region"] == "shin"
    assert region["side"] == "left"
    assert "左すね" in result["reason_ja"]
    assert "7日以内に5以上" in result["reason_ja"]


@pytest.mark.unit
def test_two_reports_separated_by_zero_still_consecutive_rule_reads_latest_two() -> (
    None
):
    """4 (d-6), 0 (d-3), 3 (d): the latest two are 0 and 3 -> no flag."""
    result = evaluate_symptom_rule(
        [_row(6, 4), _row(3, 0), _row(0, 3)],
        str(_TODAY),
    )

    assert result["flag"] is False
    assert result["flagged_regions"] == []


@pytest.mark.unit
def test_side_is_part_of_the_key() -> None:
    """Left calf 3 then right calf 3 are two regions, not a streak."""
    result = evaluate_symptom_rule(
        [_row(2, 3, side="left"), _row(0, 3, side="right")],
        str(_TODAY),
    )

    assert result["flag"] is False


@pytest.mark.unit
def test_asked_today_and_clear_today() -> None:
    """A severity-0 'other' row dated today records an explicit all-clear."""
    result = evaluate_symptom_rule(
        [_row(0, 0, body_region="other", side=None)], str(_TODAY)
    )

    assert result["flag"] is False
    assert result["asked_today"] is True
    assert result["clear_today"] is True
    assert result["recently_cleared"] is True
    assert result["days_since_last_report"] == 0
    assert result["date"] == str(_TODAY)


@pytest.mark.unit
def test_empty_rows() -> None:
    """No rows at all: not asked, nothing to flag, and the reason says so."""
    result = evaluate_symptom_rule([], str(_TODAY))

    assert result["flag"] is False
    assert result["flagged_regions"] == []
    assert result["asked_today"] is False
    assert result["clear_today"] is False
    assert result["days_since_last_report"] is None
    assert "症状記録なし" in result["reason_ja"]


@pytest.mark.unit
def test_same_day_rows_count_as_one_report() -> None:
    """Two rows for one region on one day collapse to their max severity."""
    result = evaluate_symptom_rule([_row(0, 3), _row(0, 4)], str(_TODAY))

    assert result["flag"] is False  # one report, not a consecutive pair
    assert result["asked_today"] is True


@pytest.mark.unit
def test_acute_outside_7_day_window_does_not_flag() -> None:
    """A severity-5 report 8 days ago is outside the acute window."""
    result = evaluate_symptom_rule([_row(8, 5)], str(_TODAY))

    assert result["flag"] is False
    assert result["days_since_last_report"] == 8
