"""Training-load (ACWR) DB reader.

Computes the Acute:Chronic Workload Ratio (ACWR), an established injury-risk
proxy, directly from ``activities``. The load metric is **distance only** in v1:
the daily load is the sum of ``total_distance_km`` for that day.

Why distance, not HR/TRIMP: ``avg_heart_rate`` is null for many older-device
activities, and HR/TRIMP weighting depends on max/rest HR (which clashes with the
project's "no HR formulas" stance). Distance-based ACWR needs only
``total_distance_km`` + ``activity_date``, so it is robust and HR-independent.
HR/duration weighting (TRIMP-style) is a deliberate follow-up.

ACWR = acute (last-7-day load sum) / chronic (last-28-day load sum / 4 = weekly
average). Status thresholds: <0.8 ``undertraining`` / 0.8-1.3 ``optimal`` /
1.3-1.5 ``caution`` / >1.5 ``high_risk``; chronic == 0 -> ``insufficient_data``
with ``acwr = None``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.utils.week import get_week_start_day, week_start

logger = logging.getLogger(__name__)

LOAD_METRIC = "distance_km"

# Status thresholds on the ACWR value (acute / chronic-weekly).
_UNDERTRAINING_MAX = 0.8
_OPTIMAL_MAX = 1.3
_CAUTION_MAX = 1.5


def _classify(acwr: float | None) -> str:
    """Map an ACWR value to its injury-risk status label.

    ``None`` (no chronic load) -> ``insufficient_data``.
    """
    if acwr is None:
        return "insufficient_data"
    if acwr < _UNDERTRAINING_MAX:
        return "undertraining"
    if acwr <= _OPTIMAL_MAX:
        return "optimal"
    if acwr <= _CAUTION_MAX:
        return "caution"
    return "high_risk"


def _acwr_from_loads(acute_7d: float, chronic_28d_total: float) -> float | None:
    """Compute ACWR from a 7-day acute sum and a 28-day chronic total.

    Chronic is normalized to a weekly average (28-day total / 4). Returns
    ``None`` when the chronic weekly average is zero (no baseline).
    """
    chronic_weekly = chronic_28d_total / 4.0
    if chronic_weekly == 0:
        return None
    return acute_7d / chronic_weekly


class TrainingLoadReader(BaseDBReader):
    """Reads distance-based training load (ACWR) from DuckDB ``activities``."""

    def get_acwr(self, end_date: str | None = None) -> dict[str, Any]:
        """Compute the ACWR as of ``end_date`` (inclusive).

        The daily load is the sum of ``total_distance_km`` for that day (days
        with no activity contribute 0). Acute = the last-7-day load sum (the 7
        days ending on ``end_date``); chronic = the last-28-day load sum divided
        by 4 (the weekly average).

        Args:
            end_date: ``YYYY-MM-DD`` reference day. Defaults to the latest
                ``activity_date`` in ``activities`` (None when the table is
                empty, which yields ``insufficient_data``).

        Returns:
            Dict with keys:
            - ``end_date``: ``YYYY-MM-DD`` | None
            - ``acute_load_7d``: float (km in the last 7 days)
            - ``chronic_load_28d_weekly``: float (last-28-day km / 4)
            - ``acwr``: float | None (None when chronic weekly == 0)
            - ``status``: undertraining | optimal | caution | high_risk |
              insufficient_data
            - ``load_metric``: ``"distance_km"``
        """
        resolved_end = self._resolve_end_date(end_date)
        if resolved_end is None:
            return {
                "end_date": None,
                "acute_load_7d": 0.0,
                "chronic_load_28d_weekly": 0.0,
                "acwr": None,
                "status": "insufficient_data",
                "load_metric": LOAD_METRIC,
            }

        # 28-day window ending on resolved_end (inclusive): 28 days total.
        chronic_start = resolved_end - timedelta(days=27)
        acute_start = resolved_end - timedelta(days=6)

        daily = self._daily_loads(chronic_start, resolved_end)
        chronic_total = sum(daily.values())
        acute_total = sum(km for day, km in daily.items() if day >= acute_start)

        acwr = _acwr_from_loads(acute_total, chronic_total)

        return {
            "end_date": resolved_end.strftime("%Y-%m-%d"),
            "acute_load_7d": round(acute_total, 2),
            "chronic_load_28d_weekly": round(chronic_total / 4.0, 2),
            "acwr": round(acwr, 2) if acwr is not None else None,
            "status": _classify(acwr),
            "load_metric": LOAD_METRIC,
        }

    def get_load_trend(
        self, lookback_weeks: int = 12, end_date: str | None = None
    ) -> dict[str, Any]:
        """Return the weekly load and ACWR over the trailing ``lookback_weeks``.

        Buckets are **calendar weeks** aligned to the configured week-start day
        (``athlete_profile.week_start_day``; Monday by default). The most recent
        bucket runs from its week-start through ``end_date`` and is therefore a
        partial week when ``end_date`` is not the last day of the week. Older
        buckets are full 7-day calendar weeks. For every week the ACWR is the
        acute (that week's load) divided by the chronic weekly average computed
        from the 28 days ending on that bucket's last day. The rolling ACWR
        windows themselves (see :meth:`get_acwr`) are unchanged.

        Args:
            lookback_weeks: Number of trailing weekly buckets (default 12).
            end_date: ``YYYY-MM-DD`` reference day. Defaults to the latest
                ``activity_date`` in ``activities``.

        Returns:
            Dict with keys:
            - ``weeks``: list of {week_start (YYYY-MM-DD), load_km, acwr
              (float | None), status} ordered oldest -> newest
            - ``load_metric``: ``"distance_km"``
        """
        resolved_end = self._resolve_end_date(end_date)
        if resolved_end is None or lookback_weeks <= 0:
            return {"weeks": [], "load_metric": LOAD_METRIC}

        with self._get_connection() as conn:
            start_day = get_week_start_day(conn)

        # Newest bucket starts on the week-start day of resolved_end; older
        # buckets step back 7 days each.
        current_week_start = week_start(resolved_end, start_day)
        oldest_week_start = current_week_start - timedelta(
            days=7 * (lookback_weeks - 1)
        )
        # Pull every daily load once: from 27 days before the oldest bucket's
        # last day (for that bucket's chronic window) through resolved_end.
        history_start = oldest_week_start - timedelta(days=27)
        daily = self._daily_loads(history_start, resolved_end)

        weeks: list[dict[str, Any]] = []
        # Iterate oldest -> newest so the array reads chronologically.
        for i in range(lookback_weeks - 1, -1, -1):
            bucket_start = current_week_start - timedelta(days=7 * i)
            # The newest bucket is capped at resolved_end (a partial week);
            # older buckets are full calendar weeks.
            bucket_end = min(bucket_start + timedelta(days=6), resolved_end)
            chronic_start = bucket_end - timedelta(days=27)

            acute_total = sum(
                km for day, km in daily.items() if bucket_start <= day <= bucket_end
            )
            chronic_total = sum(
                km for day, km in daily.items() if chronic_start <= day <= bucket_end
            )
            acwr = _acwr_from_loads(acute_total, chronic_total)

            weeks.append(
                {
                    "week_start": bucket_start.strftime("%Y-%m-%d"),
                    "load_km": round(acute_total, 2),
                    "acwr": round(acwr, 2) if acwr is not None else None,
                    "status": _classify(acwr),
                }
            )

        return {"weeks": weeks, "load_metric": LOAD_METRIC}

    def _resolve_end_date(self, end_date: str | None) -> date | None:
        """Return the reference end date as a ``date``.

        When ``end_date`` is given, parse it. Otherwise fall back to the latest
        ``activity_date`` in ``activities`` (None when the table is empty).
        """
        if end_date is not None:
            return datetime.strptime(end_date, "%Y-%m-%d").date()

        with self._get_connection() as conn:
            row = conn.execute("SELECT max(activity_date) FROM activities").fetchone()
        if row is None or row[0] is None:
            return None
        latest = row[0]
        # DuckDB returns datetime.date for a DATE column.
        return (
            latest
            if isinstance(latest, date)
            else datetime.strptime(str(latest), "%Y-%m-%d").date()
        )

    def _daily_loads(self, start: date, end: date) -> dict[date, float]:
        """Sum ``total_distance_km`` per day in ``[start, end]`` (single query).

        Days with no activity are simply absent from the mapping (treated as 0
        load by callers). HR-independent: never reads ``avg_heart_rate``.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT activity_date, COALESCE(sum(total_distance_km), 0.0)
                FROM activities
                WHERE activity_date BETWEEN ? AND ?
                GROUP BY activity_date
                """,
                [start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")],
            ).fetchall()

        loads: dict[date, float] = {}
        for activity_date, total_km in rows:
            day = (
                activity_date
                if isinstance(activity_date, date)
                else datetime.strptime(str(activity_date), "%Y-%m-%d").date()
            )
            loads[day] = float(total_km or 0.0)
        return loads
