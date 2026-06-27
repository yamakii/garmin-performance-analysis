"""Shared week boundary utilities with a configurable start day.

The athlete's preferred week start day is stored per-user in
``athlete_profile.week_start_day`` (0=Monday … 6=Sunday, following
``datetime.date.weekday()``). These helpers compute the start (and inclusive
7-day bounds) of the week containing a given date for any start day, so every
feature shares a single, consistent week definition.
"""

from __future__ import annotations

from datetime import date, timedelta

DEFAULT_WEEK_START_DAY = 0  # 0=Monday … 6=Sunday (date.weekday() convention)


def week_start(d: date, start_day: int = DEFAULT_WEEK_START_DAY) -> date:
    """Return the start date of the week containing ``d``.

    Args:
        d: Any date within the target week.
        start_day: Weekday the week begins on (0=Monday … 6=Sunday). Defaults
            to ``DEFAULT_WEEK_START_DAY`` (Monday).

    Returns:
        The date of the most recent ``start_day`` on or before ``d``. When ``d``
        already falls on ``start_day``, ``d`` itself is returned.
    """
    offset = (d.weekday() - start_day) % 7
    return d - timedelta(days=offset)


def week_bounds(d: date, start_day: int = DEFAULT_WEEK_START_DAY) -> tuple[date, date]:
    """Return the inclusive ``(start, end)`` bounds of the week containing ``d``.

    Args:
        d: Any date within the target week.
        start_day: Weekday the week begins on (0=Monday … 6=Sunday). Defaults
            to ``DEFAULT_WEEK_START_DAY`` (Monday).

    Returns:
        A ``(start, end)`` tuple where ``start`` is :func:`week_start` and
        ``end`` is ``start + 6`` days (the inclusive last day of the week).
    """
    start = week_start(d, start_day)
    return start, start + timedelta(days=6)
