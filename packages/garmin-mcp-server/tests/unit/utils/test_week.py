"""Unit tests for the shared week boundary utilities (utils/week.py)."""

from datetime import date

import pytest

from garmin_mcp.utils.week import DEFAULT_WEEK_START_DAY, week_bounds, week_start


@pytest.mark.unit
def test_default_week_start_day_is_monday() -> None:
    """The default start day follows date.weekday() (0 = Monday)."""
    assert DEFAULT_WEEK_START_DAY == 0


@pytest.mark.unit
def test_week_start_monday_default() -> None:
    """Wednesday with Monday start -> the preceding Monday."""
    assert week_start(date(2026, 6, 24)) == date(2026, 6, 22)


@pytest.mark.unit
def test_week_start_sunday_config() -> None:
    """Wednesday with Sunday start (6) -> the preceding Sunday."""
    assert week_start(date(2026, 6, 24), start_day=6) == date(2026, 6, 21)


@pytest.mark.unit
def test_week_start_on_boundary_day() -> None:
    """A date that already falls on the start day returns itself."""
    assert week_start(date(2026, 6, 22), start_day=0) == date(2026, 6, 22)


@pytest.mark.unit
def test_week_start_sunday_input_monday_week() -> None:
    """Sunday with Monday start belongs to the prior week (previous Monday)."""
    assert week_start(date(2026, 6, 21), start_day=0) == date(2026, 6, 15)


@pytest.mark.unit
def test_week_bounds_monday() -> None:
    """Monday-start bounds span the inclusive Mon..Sun range."""
    assert week_bounds(date(2026, 6, 24), start_day=0) == (
        date(2026, 6, 22),
        date(2026, 6, 28),
    )


@pytest.mark.unit
def test_week_bounds_end_is_start_plus_6() -> None:
    """For any input/start_day, end is always start + 6 days."""
    for day in range(7):
        start, end = week_bounds(date(2026, 6, 24), start_day=day)
        assert (end - start).days == 6
