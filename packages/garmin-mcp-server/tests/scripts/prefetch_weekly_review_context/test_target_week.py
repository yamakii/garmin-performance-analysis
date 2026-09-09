"""resolve_target_week() and weeks_to_race()."""

from __future__ import annotations

from datetime import date

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _resolve_target_week,
    _weeks_to_race,
)


@pytest.mark.unit
def test_resolve_target_week_default_midweek() -> None:
    """None target mid-week -> the current (in-progress) week."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 6), date(2026, 7, 12))
    assert (ps, pe) == (date(2026, 6, 29), date(2026, 7, 5))
    assert in_progress is True


@pytest.mark.unit
def test_resolve_target_week_default_last_day() -> None:
    """None target on the last day (Sunday) -> next week, not in progress."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 6, 14), 0)
    assert (ws, we) == (date(2026, 6, 15), date(2026, 6, 21))
    assert (ps, pe) == (date(2026, 6, 8), date(2026, 6, 14))
    assert in_progress is False


@pytest.mark.unit
def test_resolve_target_week_this() -> None:
    """'this' -> the week containing today."""
    ws, we, _ps, _pe, _ip = _resolve_target_week("this", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 6), date(2026, 7, 12))


@pytest.mark.unit
def test_resolve_target_week_next() -> None:
    """'next' -> the week after the one containing today."""
    ws, we, _ps, _pe, in_progress = _resolve_target_week("next", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 7, 13), date(2026, 7, 19))
    assert in_progress is False


@pytest.mark.unit
def test_resolve_target_week_explicit() -> None:
    """An explicit YYYY-MM-DD -> the week containing that date."""
    ws, we, _ps, _pe, _ip = _resolve_target_week("2026-06-16", date(2026, 7, 10), 0)
    assert (ws, we) == (date(2026, 6, 15), date(2026, 6, 21))


@pytest.mark.unit
def test_resolve_target_week_sunday_start() -> None:
    """Sunday-start weeks: Saturday is the last day -> next week's bounds."""
    ws, we, ps, pe, in_progress = _resolve_target_week(None, date(2026, 6, 20), 6)
    assert (ws, we) == (date(2026, 6, 21), date(2026, 6, 27))
    assert (ps, pe) == (date(2026, 6, 14), date(2026, 6, 20))
    assert in_progress is False


@pytest.mark.unit
def test_weeks_to_race_confirmed() -> None:
    """A confirmed race date -> ceil((race - week_start) / 7) whole weeks."""
    assert _weeks_to_race("2026-10-11", date(2026, 7, 6)) == 14


@pytest.mark.unit
def test_weeks_to_race_null() -> None:
    """A missing race date -> None (unconfirmed race)."""
    assert _weeks_to_race(None, date(2026, 7, 6)) is None
