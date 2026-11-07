"""Read a commute run off its start time and its start / end points (#1522).

A run home from work is often run with a backpack, at the end of a working
day, from a place that is not home. Read as a normal run, its higher heart
rate, shorter stride and lower cadence look like a fitness or form change.
When the athlete has not said what the run was, this guess flags it so the
coach can treat the signals with care instead of building a story on them.

The rule is deliberately narrow: a weekday run that starts in the evening and
ends somewhere else than it started. An out-and-back or a loop from home ends
where it started, a weekend run is not a commute, and a run without GPS on
both ends cannot be read at all -- each of those is ``False``.

The inference is read-time only: it is never written to the database, so a
change to this rule changes every past report without a backfill, and an
athlete-stated ``commute`` row always wins over it.
"""

from __future__ import annotations

import math
from datetime import datetime

#: Start and end further apart than this (km) is a point-to-point run.
COMMUTE_MIN_DISPLACEMENT_KM = 1.5

#: Earliest local start hour of an evening commute home.
COMMUTE_EARLIEST_LOCAL_HOUR = 17

# Monday..Friday as ``datetime.weekday()`` values.
_WORKDAYS = frozenset(range(5))

# Mean Earth radius (km) for the haversine distance.
_EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two ``(lat, lon)`` points in km.

    Args:
        a: ``(latitude, longitude)`` in degrees.
        b: ``(latitude, longitude)`` in degrees.

    Returns:
        The distance in kilometres.
    """
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def infer_commute(
    start_time_local: datetime,
    start_latlon: tuple[float, float] | None,
    end_latlon: tuple[float, float] | None,
) -> bool:
    """Whether a run looks like a commute home (weekday evening, point to point).

    Args:
        start_time_local: The run's local start time.
        start_latlon: The first GPS fix ``(lat, lon)``, or ``None``.
        end_latlon: The last GPS fix ``(lat, lon)``, or ``None``.

    Returns:
        ``True`` for a Monday-Friday run starting at or after
        :data:`COMMUTE_EARLIEST_LOCAL_HOUR` whose start and end points are
        more than :data:`COMMUTE_MIN_DISPLACEMENT_KM` apart; ``False``
        otherwise, including when either GPS point is missing.
    """
    if start_latlon is None or end_latlon is None:
        return False
    if start_time_local.weekday() not in _WORKDAYS:
        return False
    if start_time_local.hour < COMMUTE_EARLIEST_LOCAL_HOUR:
        return False
    return haversine_km(start_latlon, end_latlon) > COMMUTE_MIN_DISPLACEMENT_KM
