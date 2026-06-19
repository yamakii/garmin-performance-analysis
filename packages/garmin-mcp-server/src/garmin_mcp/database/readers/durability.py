"""Durability (cardiac-decoupling) DB reader.

Quantifies an athlete's "muscular endurance / fade resistance" over long runs
by computing **cardiac decoupling**: the ratio of the second-half HR/speed
efficiency to the first-half HR/speed efficiency. ``>5%`` is a common rule of
thumb for insufficient aerobic durability.

This is the *longitudinal* counterpart to the per-activity second-half form
decay analysis (#61, split-section-analyst). v1 focuses on decoupling and pace
fade only; second-half *form* decay (GCT/VO/VR) is already covered per-activity
by #61 and is intentionally out of scope here.

Definitions (per activity, using ``time_series_metrics``):

- The activity is split in two at the **timestamp midpoint**
  ``(min(timestamp_s) + max(timestamp_s)) / 2``.
- ``hr_speed_ratio`` for a half = ``avg(heart_rate) / avg(speed)`` (beats per
  metre/second; higher means more cardiac cost per unit speed).
- ``decoupling_pct`` = ``(back_ratio / front_ratio) - 1`` as a percentage.
  Positive means the second half costs more HR per unit speed (fade).
- ``pace_fade_pct`` = ``(back_pace / front_pace) - 1`` as a percentage, where
  pace = ``1 / avg_speed``; this reduces to ``front_speed / back_speed - 1``.

Returns ``None`` for an activity when HR or speed is missing or the midpoint
cannot split the series into two non-empty halves (HR-data-dependent).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import numpy as np
from scipy import stats

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)

# Significance threshold for declaring a non-stable durability trend.
_P_VALUE_THRESHOLD = 0.05


class DurabilityReader(BaseDBReader):
    """Reads long-run cardiac decoupling / pace fade from DuckDB."""

    def get_activity_durability(self, activity_id: int) -> dict[str, Any] | None:
        """Compute first-half vs second-half decoupling for one activity.

        The time series is split at the timestamp midpoint. Each half's average
        heart rate and speed are aggregated in SQL; decoupling and pace fade are
        derived from those.

        Args:
            activity_id: Activity ID.

        Returns:
            ``None`` when HR or speed data is missing, or when the midpoint
            cannot produce two non-empty halves. Otherwise a dict::

                {
                    "activity_id": int,
                    "activity_date": "YYYY-MM-DD",
                    "distance_km": float,
                    "decoupling_pct": float,  # (back HR/spd)/(front HR/spd)-1, %
                    "pace_fade_pct": float,   # back_pace/front_pace-1, %
                }
        """
        with self._get_connection() as conn:
            bounds = conn.execute(
                """
                SELECT min(timestamp_s), max(timestamp_s)
                FROM time_series_metrics
                WHERE activity_id = ?
                  AND heart_rate IS NOT NULL
                  AND speed IS NOT NULL
                  AND speed > 0
                """,
                [activity_id],
            ).fetchone()

            if bounds is None or bounds[0] is None or bounds[1] is None:
                return None
            min_ts, max_ts = int(bounds[0]), int(bounds[1])
            if max_ts <= min_ts:
                return None

            midpoint = (min_ts + max_ts) / 2.0

            # First half: [min_ts, midpoint); second half: [midpoint, max_ts].
            halves = conn.execute(
                """
                SELECT
                    avg(CASE WHEN timestamp_s < ? THEN heart_rate END) AS front_hr,
                    avg(CASE WHEN timestamp_s < ? THEN speed END) AS front_speed,
                    avg(CASE WHEN timestamp_s >= ? THEN heart_rate END) AS back_hr,
                    avg(CASE WHEN timestamp_s >= ? THEN speed END) AS back_speed
                FROM time_series_metrics
                WHERE activity_id = ?
                  AND heart_rate IS NOT NULL
                  AND speed IS NOT NULL
                  AND speed > 0
                """,
                [midpoint, midpoint, midpoint, midpoint, activity_id],
            ).fetchone()

        if halves is None or any(v is None for v in halves):
            return None

        front_hr, front_speed, back_hr, back_speed = (float(v) for v in halves)
        if front_speed <= 0 or back_speed <= 0 or front_hr <= 0:
            return None

        front_ratio = front_hr / front_speed
        back_ratio = back_hr / back_speed
        if front_ratio <= 0:
            return None

        decoupling_pct = (back_ratio / front_ratio - 1.0) * 100.0
        # pace = 1 / speed, so back_pace / front_pace = front_speed / back_speed.
        pace_fade_pct = (front_speed / back_speed - 1.0) * 100.0

        activity_date = self._activity_date(activity_id)
        distance_km = self._distance_km(activity_id)

        return {
            "activity_id": activity_id,
            "activity_date": activity_date,
            "distance_km": distance_km,
            "decoupling_pct": round(decoupling_pct, 2),
            "pace_fade_pct": round(pace_fade_pct, 2),
        }

    def get_durability_trend(
        self,
        start_date: str,
        end_date: str,
        min_distance_km: float = 15.0,
    ) -> dict[str, Any]:
        """Return the decoupling trend across long runs in a date window.

        Only activities with ``total_distance_km >= min_distance_km`` are
        considered (short runs are excluded). The decoupling regression x-axis
        is **days elapsed** since the earliest qualifying activity (not the
        activity index), so unequal date spacing is handled correctly (#341).

        Args:
            start_date: Inclusive window start (``YYYY-MM-DD``).
            end_date: Inclusive window end (``YYYY-MM-DD``).
            min_distance_km: Minimum distance to qualify as a long run.

        Returns:
            Dict::

                {
                    "activities": [<get_activity_durability(...) non-null>, ...],
                        # ordered by activity_date ascending
                    "trend": {
                        "decoupling_slope_per_day": float,
                        "data_points": int,
                        "direction": "improving" | "worsening" | "stable"
                                     | "insufficient_data",
                    },
                }

            ``direction`` is ``improving`` when decoupling falls over time
            (slope < 0 and p < 0.05), ``worsening`` when it rises significantly,
            ``stable`` when not significant, and ``insufficient_data`` with
            ``slope = 0.0`` when fewer than 2 qualifying activities exist.
        """
        long_run_ids = self._long_run_ids(start_date, end_date, min_distance_km)

        activities: list[dict[str, Any]] = []
        for activity_id in long_run_ids:
            result = self.get_activity_durability(activity_id)
            if result is not None:
                activities.append(result)

        # Order chronologically by activity_date (ascending).
        activities.sort(key=lambda a: a["activity_date"])

        trend = self._build_trend(activities)
        return {"activities": activities, "trend": trend}

    def _build_trend(self, activities: list[dict[str, Any]]) -> dict[str, Any]:
        """Regress decoupling on elapsed days; classify the trend direction."""
        if len(activities) < 2:
            return {
                "decoupling_slope_per_day": 0.0,
                "data_points": len(activities),
                "direction": "insufficient_data",
            }

        ordinals = [
            datetime.strptime(a["activity_date"], "%Y-%m-%d").date().toordinal()
            for a in activities
        ]
        base = ordinals[0]
        x = np.array([o - base for o in ordinals], dtype=float)
        y = [a["decoupling_pct"] for a in activities]

        slope, _intercept, _r, p_value, _std_err = stats.linregress(x, y)

        if p_value > _P_VALUE_THRESHOLD:
            direction = "stable"
        elif slope < 0:
            direction = "improving"  # decoupling falling = better durability
        else:
            direction = "worsening"

        return {
            "decoupling_slope_per_day": float(slope),
            "data_points": len(activities),
            "direction": direction,
        }

    def _long_run_ids(
        self, start_date: str, end_date: str, min_distance_km: float
    ) -> list[int]:
        """Return qualifying long-run activity IDs in the window (date ascending)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT activity_id
                FROM activities
                WHERE activity_date BETWEEN ? AND ?
                  AND total_distance_km >= ?
                ORDER BY activity_date ASC, activity_id ASC
                """,
                [start_date, end_date, min_distance_km],
            ).fetchall()
        return [int(row[0]) for row in rows]

    def _activity_date(self, activity_id: int) -> str | None:
        """Return the activity's date as a ``YYYY-MM-DD`` string (or None)."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT activity_date FROM activities WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
        if row is None or row[0] is None:
            return None
        value = row[0]
        # DuckDB returns datetime.date for a DATE column.
        return value.strftime("%Y-%m-%d") if isinstance(value, date) else str(value)

    def _distance_km(self, activity_id: int) -> float | None:
        """Return the activity's total distance in km (or None)."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT total_distance_km FROM activities WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])
