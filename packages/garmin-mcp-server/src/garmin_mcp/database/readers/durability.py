"""Durability (cardiac-decoupling) DB reader.

Quantifies an athlete's "muscular endurance / fade resistance" over long runs
by computing **cardiac decoupling**: the ratio of the second-half HR/speed
efficiency to the first-half HR/speed efficiency. ``>5%`` is a common rule of
thumb for insufficient aerobic durability.

This is the *longitudinal* counterpart to the per-activity second-half form
decay analysis (#61, split-section-analyst). Alongside cardiac decoupling and
pace fade, the reader now also tracks second-half **form** decay (#368): how
ground-contact time, vertical oscillation and vertical ratio worsen from the
first to the second half of a long run, and whether that degradation trends
worse over time. Together (cardiac + muscular) they give the complete fatigue
picture for durability-focused training.

Definitions (per activity, using ``time_series_metrics``):

- The activity is split in two at the **timestamp midpoint**
  ``(min(timestamp_s) + max(timestamp_s)) / 2``.
- ``hr_speed_ratio`` for a half = ``avg(heart_rate) / avg(speed)`` (beats per
  metre/second; higher means more cardiac cost per unit speed).
- ``decoupling_pct`` = ``(back_ratio / front_ratio) - 1`` as a percentage.
  Positive means the second half costs more HR per unit speed (fade).
- ``pace_fade_pct`` = ``(back_pace / front_pace) - 1`` as a percentage, where
  pace = ``1 / avg_speed``; this reduces to ``front_speed / back_speed - 1``.
- ``gct_fade_pct`` / ``vo_fade_pct`` / ``vr_fade_pct`` = ``(back / front) - 1``
  as a percentage for ground-contact time, vertical oscillation and vertical
  ratio respectively. Positive means form worsened in the second half. These
  are **independent and nullable**: older devices lack GCT/VO/VR, so a null
  form metric is reported as ``None`` and never blocks decoupling computation.

Returns ``None`` for an activity when HR or speed is missing or the midpoint
cannot split the series into two non-empty halves (HR-data-dependent). Form
fades are computed independently within that activity and may individually be
``None`` without affecting decoupling.
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

# Absolute-level decoupling bands (lower = better aerobic durability). ``>5%`` is
# a common rule of thumb for insufficient aerobic durability (see module
# docstring), so ``<5%`` = strong, ``5-10%`` = moderate, ``>=10%`` = poor. These
# let the narration frame a slope-based direction against the actual level
# rather than crying "worsening" while every long run is still excellent (#845).
_STRONG_BAND_MAX = 5.0
_MODERATE_BAND_MAX = 10.0


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
                    "gct_fade_pct": float | None,  # (back_gct/front_gct-1), %
                    "vo_fade_pct": float | None,   # (back_vo/front_vo-1), %
                    "vr_fade_pct": float | None,   # (back_vr/front_vr-1), %
                }

            The three form-fade fields are ``None`` when either half lacks a
            non-null average for that metric (older devices), independently of
            the always-present decoupling/pace-fade fields.
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
            # Form metrics (GCT/VO/VR) are averaged on the SAME midpoint split
            # but are intentionally NOT in the WHERE NOT NULL filters: they are
            # independent of HR/speed and may be null on older devices.
            halves = conn.execute(
                """
                SELECT
                    avg(CASE WHEN timestamp_s < ? THEN heart_rate END) AS front_hr,
                    avg(CASE WHEN timestamp_s < ? THEN speed END) AS front_speed,
                    avg(CASE WHEN timestamp_s >= ? THEN heart_rate END) AS back_hr,
                    avg(CASE WHEN timestamp_s >= ? THEN speed END) AS back_speed,
                    avg(CASE WHEN timestamp_s < ? THEN ground_contact_time END)
                        AS front_gct,
                    avg(CASE WHEN timestamp_s >= ? THEN ground_contact_time END)
                        AS back_gct,
                    avg(CASE WHEN timestamp_s < ? THEN vertical_oscillation END)
                        AS front_vo,
                    avg(CASE WHEN timestamp_s >= ? THEN vertical_oscillation END)
                        AS back_vo,
                    avg(CASE WHEN timestamp_s < ? THEN vertical_ratio END)
                        AS front_vr,
                    avg(CASE WHEN timestamp_s >= ? THEN vertical_ratio END)
                        AS back_vr
                FROM time_series_metrics
                WHERE activity_id = ?
                  AND heart_rate IS NOT NULL
                  AND speed IS NOT NULL
                  AND speed > 0
                """,
                [midpoint] * 10 + [activity_id],
            ).fetchone()

        if halves is None:
            return None

        (
            raw_front_hr,
            raw_front_speed,
            raw_back_hr,
            raw_back_speed,
            front_gct,
            back_gct,
            front_vo,
            back_vo,
            front_vr,
            back_vr,
        ) = halves

        # Decoupling/pace fade require all four HR/speed averages (HR-dependent).
        if any(
            v is None
            for v in (raw_front_hr, raw_front_speed, raw_back_hr, raw_back_speed)
        ):
            return None

        front_hr, front_speed, back_hr, back_speed = (
            float(raw_front_hr),
            float(raw_front_speed),
            float(raw_back_hr),
            float(raw_back_speed),
        )
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
            "gct_fade_pct": self._fade_pct(front_gct, back_gct),
            "vo_fade_pct": self._fade_pct(front_vo, back_vo),
            "vr_fade_pct": self._fade_pct(front_vr, back_vr),
        }

    @staticmethod
    def _fade_pct(front: Any, back: Any) -> float | None:
        """Return ``(back/front - 1) * 100`` (rounded) or ``None``.

        ``None`` when either half average is null (decoupled metric absent) or
        the front average is non-positive (cannot form a meaningful ratio).
        """
        if front is None or back is None:
            return None
        front_f = float(front)
        if front_f <= 0:
            return None
        return round((float(back) / front_f - 1.0) * 100.0, 2)

    def get_durability_trend(
        self,
        start_date: str,
        end_date: str,
        min_distance_km: float = 10.0,
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
                        "gct_fade_slope_per_day": float | None,
                        "form_direction": "improving" | "worsening" | "stable"
                                          | "insufficient_data",
                        "best_run": {...} | None,   # lowest decoupling
                        "worst_run": {...} | None,  # highest decoupling
                        "metric_directions": {...}, # sign-convention labels
                        "absolute_assessment": {    # level, not slope
                            "recent_decoupling_pct": float,
                            "window_median_decoupling_pct": float,
                            "band": "strong" | "moderate" | "poor",
                            "all_within_strong_band": bool,
                        } | None,
                        "fragile": bool,            # direction hinges on 1 point
                        "fragile_reason": {...} | None,
                        "direction_caveat": str | None,  # English; None if none
                    },
                }

            ``best_run`` / ``worst_run`` rank the runs by cardiac
            ``decoupling_pct`` (lower = better durability) and are ``None`` when
            fewer than 2 activities exist. ``metric_directions`` labels the sign
            conventions and is always present. See ``_build_durability_ranking``.
            These are descriptive and computed regardless of the ``<3``-point
            regression significance gate.

            ``direction`` is ``improving`` when decoupling falls over time
            (slope < 0 and p < 0.05), ``worsening`` when it rises significantly,
            ``stable`` when not significant, and ``insufficient_data`` with
            ``slope = 0.0`` when fewer than 3 qualifying activities exist.

            ``form_direction`` applies the same classification to the GCT-fade
            regression (over activities with a non-null ``gct_fade_pct``).
            ``gct_fade_slope_per_day`` is ``None`` (and ``form_direction`` is
            ``insufficient_data``) when fewer than 3 such activities exist.

            ``absolute_assessment`` describes the window's *level* (not slope) so
            a worsening slope can be read against the actual band; it is ``None``
            only for an empty window. ``fragile`` is ``True`` when the significant
            direction hinges on a single leverage point (a removal that flips the
            classification); ``fragile_reason`` names the most slope-influential
            run and how significance changes without it (or, at exactly 3 points,
            a not-gate-testable note). ``direction_caveat`` is an English one-line
            caveat (rendered to Japanese by the narration layer) present only when
            the slope direction may mislead — a worsening slope while every run is
            in the strong band, or a fragile direction; otherwise ``None`` (#845).
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
        # Ranking is descriptive (which run held up best), independent of the
        # <3-point regression significance gate, so it is merged unconditionally.
        trend.update(self._build_durability_ranking(activities))
        return {"activities": activities, "trend": trend}

    def _build_durability_ranking(
        self, activities: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Rank long runs by cardiac decoupling (lower = better durability).

        pace_fade is intentionally excluded from ranking (it is a pacing-strategy
        descriptor, not a durability measure). Returns::

            {
                "best_run": {...} | None,
                "worst_run": {...} | None,
                "metric_directions": {
                    "decoupling_pct": "lower_is_better",
                    "pace_fade_pct":
                        "descriptor_negative_means_faster_second_half",
                },
            }

        ``best_run`` / ``worst_run`` are ``{activity_id, activity_date,
        decoupling_pct, pace_fade_pct}`` ranked by ``decoupling_pct`` ascending
        (lower = better), tie-broken deterministically by ``(decoupling_pct,
        activity_date, activity_id)``. Both are ``None`` when fewer than 2
        activities exist (cannot rank). ``metric_directions`` is always present.
        """
        metric_directions = {
            "decoupling_pct": "lower_is_better",
            "pace_fade_pct": "descriptor_negative_means_faster_second_half",
        }
        if len(activities) < 2:
            return {
                "best_run": None,
                "worst_run": None,
                "metric_directions": metric_directions,
            }

        ranked = sorted(
            activities,
            key=lambda a: (
                a["decoupling_pct"],
                a["activity_date"],
                a["activity_id"],
            ),
        )
        return {
            "best_run": self._durability_run_summary(ranked[0]),
            "worst_run": self._durability_run_summary(ranked[-1]),
            "metric_directions": metric_directions,
        }

    @staticmethod
    def _durability_run_summary(activity: dict[str, Any]) -> dict[str, Any]:
        """Project an activity down to the ranking-relevant durability fields."""
        return {
            "activity_id": activity["activity_id"],
            "activity_date": activity["activity_date"],
            "decoupling_pct": activity["decoupling_pct"],
            "pace_fade_pct": activity["pace_fade_pct"],
        }

    def _build_trend(self, activities: list[dict[str, Any]]) -> dict[str, Any]:
        """Regress decoupling and GCT fade on elapsed days; classify direction.

        Both regressions use the SAME ordinal/base-day x-axis convention. The
        GCT-fade regression runs only over activities with a non-null
        ``gct_fade_pct`` (form metrics are decoupled and may be absent), so it
        may have fewer points than the decoupling regression.

        Requires at least 3 activities: with exactly 2 points scipy's
        ``linregress`` returns ``p_value == nan`` (df=0), and ``nan > 0.05`` is
        False, so a 2-point regression would skip the significance gate and
        confidently classify a direction from just two observations.
        """
        absolute_assessment = self._build_absolute_assessment(activities)

        if len(activities) < 3:
            return {
                "decoupling_slope_per_day": 0.0,
                "data_points": len(activities),
                "direction": "insufficient_data",
                "gct_fade_slope_per_day": None,
                "form_direction": "insufficient_data",
                "absolute_assessment": absolute_assessment,
                "fragile": False,
                "fragile_reason": None,
                "direction_caveat": None,
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

        gct_slope, form_direction = self._regress_form(activities, ordinals, base)

        # A slope-based direction can be dominated by a single leverage point
        # (e.g. an exceptional early run) and can flag "worsening" while every
        # long run is still excellent in absolute terms. Surface both so the
        # narration frames the direction correctly rather than crying wolf (#845).
        fragile, fragile_reason = self._assess_fragility(
            x, y, float(slope), direction, activities
        )
        direction_caveat = self._build_direction_caveat(
            direction, absolute_assessment, fragile, fragile_reason
        )

        return {
            "decoupling_slope_per_day": float(slope),
            "data_points": len(activities),
            "direction": direction,
            "gct_fade_slope_per_day": gct_slope,
            "form_direction": form_direction,
            "absolute_assessment": absolute_assessment,
            "fragile": fragile,
            "fragile_reason": fragile_reason,
            "direction_caveat": direction_caveat,
        }

    @staticmethod
    def _classify_band(decoupling_pct: float) -> str:
        """Classify a decoupling value into an absolute durability band.

        ``<5%`` = ``strong`` (good aerobic durability), ``5-10%`` = ``moderate``,
        ``>=10%`` = ``poor``. Lower decoupling (incl. negatives) is better.
        """
        if decoupling_pct < _STRONG_BAND_MAX:
            return "strong"
        if decoupling_pct < _MODERATE_BAND_MAX:
            return "moderate"
        return "poor"

    @classmethod
    def _build_absolute_assessment(
        cls, activities: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Summarize the window's *absolute* decoupling level (not its slope).

        ``activities`` are chronological (date ascending), so the last element is
        the most recent run. Returns ``None`` for an empty list. ``band`` is
        classified on the window median (representative level);
        ``all_within_strong_band`` is ``True`` only when every run is ``<5%``.
        """
        if not activities:
            return None
        decouplings = [float(a["decoupling_pct"]) for a in activities]
        median = float(np.median(decouplings))
        return {
            "recent_decoupling_pct": round(decouplings[-1], 2),
            "window_median_decoupling_pct": round(median, 2),
            "band": cls._classify_band(median),
            "all_within_strong_band": all(d < _STRONG_BAND_MAX for d in decouplings),
        }

    def _assess_fragility(
        self,
        x: Any,
        y: list[float],
        slope: float,
        direction: str,
        activities: list[dict[str, Any]],
    ) -> tuple[bool, dict[str, Any] | None]:
        """Flag when a significant direction hinges on a single leverage point.

        Only meaningful for a significant ``direction`` (``worsening`` /
        ``improving``); ``stable`` / ``insufficient_data`` are never fragile.

        With ``n >= 4`` we run leave-one-out: drop each point, re-regress the
        remaining ``n-1`` (``>=3``, so the significance gate is valid) and check
        whether the classified direction changes. If any single removal flips it,
        the trend is fragile. The reported leverage point is the removal that most
        influences the slope itself (largest ``|slope - slope_without|``, i.e. the
        DFBETA-style most influential run) — the point the direction leans on,
        which is typically an exceptional outlier rather than whichever removal
        merely nudges the p-value furthest. ``single_removals_that_flip`` /
        ``n_points`` let the caveat say "any single run" when every removal flips.

        With exactly ``n == 3`` a single removal leaves 2 points (``p == nan``,
        not gate-testable), so a significant 3-point trend is reported fragile
        with an explanatory note and no leverage point.
        """
        if direction not in ("worsening", "improving"):
            return False, None

        n = len(y)
        if n == 3:
            return True, {
                "leverage_point": None,
                "direction_without_leverage_point": None,
                "p_without_leverage_point": None,
                "slope_without_leverage_point": None,
                "single_removals_that_flip": None,
                "n_points": n,
                "note": (
                    "significant direction from only 3 long runs; removing any "
                    "single run leaves 2 points (p undefined), so significance "
                    "is not gate-testable and the trend is inherently fragile"
                ),
            }

        # For each single removal record (index, slope, p, direction) so we can
        # both count flips and pick the most slope-influential one.
        flips: list[tuple[int, float, float, str]] = []
        for i in range(n):
            xr = np.delete(x, i)
            yr = [v for j, v in enumerate(y) if j != i]
            slope_i, _intercept, _r, p_i, _std_err = stats.linregress(xr, yr)
            if p_i > _P_VALUE_THRESHOLD:
                dir_i = "stable"
            elif slope_i < 0:
                dir_i = "improving"
            else:
                dir_i = "worsening"
            if dir_i != direction:
                flips.append((i, float(slope_i), float(p_i), dir_i))

        if not flips:
            return False, None

        # Leverage point = the flipping removal that moves the slope the most
        # (|slope - slope_without|); this is the run the direction actually leans
        # on (the exceptional outlier), not merely the largest resulting p-value.
        idx, slope_without, p_without, dir_without = max(
            flips, key=lambda e: abs(slope - e[1])
        )
        lever = activities[idx]
        return True, {
            "leverage_point": {
                "activity_id": lever.get("activity_id"),
                "activity_date": lever["activity_date"],
                "decoupling_pct": lever["decoupling_pct"],
            },
            "direction_without_leverage_point": dir_without,
            "p_without_leverage_point": round(p_without, 3),
            "slope_without_leverage_point": round(slope_without, 4),
            "single_removals_that_flip": len(flips),
            "n_points": n,
            "note": None,
        }

    @staticmethod
    def _build_direction_caveat(
        direction: str,
        absolute_assessment: dict[str, Any] | None,
        fragile: bool,
        fragile_reason: dict[str, Any] | None,
    ) -> str | None:
        """Build an English caveat when the slope direction may mislead.

        English (like ``recovery_trend_note``); the narration layer renders it in
        Japanese. Returns ``None`` when the direction stands on its own (a
        genuine worsening with a poor absolute level, or a robust trend).
        """
        if direction not in ("worsening", "improving"):
            return None

        parts: list[str] = []
        strong = bool(
            absolute_assessment and absolute_assessment.get("all_within_strong_band")
        )
        if direction == "worsening" and strong:
            parts.append(
                "decoupling slope is worsening but every long run in the window "
                f"is within the strong band (<{_STRONG_BAND_MAX:.0f}% decoupling), "
                "so absolute aerobic durability remains strong"
            )

        if fragile and fragile_reason:
            lever = fragile_reason.get("leverage_point")
            if lever:
                n_pts = fragile_reason.get("n_points")
                n_flip = fragile_reason.get("single_removals_that_flip")
                if n_pts is not None and n_flip == n_pts:
                    # Maximally fragile: every single removal kills significance,
                    # so the direction rests on all N runs jointly.
                    parts.append(
                        f"the {direction} direction is fragile: removing any single "
                        f"long run makes it non-significant (p>{_P_VALUE_THRESHOLD}); "
                        f"it rests on all {n_pts} runs jointly and leans most on "
                        f"{lever['activity_date']} ({lever['decoupling_pct']}% "
                        "decoupling)"
                    )
                else:
                    parts.append(
                        f"the {direction} direction is fragile: removing a single "
                        f"leverage point ({lever['activity_date']}, "
                        f"{lever['decoupling_pct']}% decoupling) changes the trend "
                        f"to '{fragile_reason['direction_without_leverage_point']}' "
                        f"(p={fragile_reason['p_without_leverage_point']})"
                    )
            elif fragile_reason.get("note"):
                parts.append(
                    f"the {direction} direction is fragile: {fragile_reason['note']}"
                )

        if not parts:
            return None
        return "; ".join(parts) + "."

    def _regress_form(
        self,
        activities: list[dict[str, Any]],
        ordinals: list[int],
        base: int,
    ) -> tuple[float | None, str]:
        """Regress ``gct_fade_pct`` on elapsed days over non-null form points.

        Returns ``(slope_per_day, form_direction)``. ``slope`` is ``None`` and
        the direction is ``insufficient_data`` when fewer than 3 activities have
        a non-null ``gct_fade_pct`` (with exactly 2 points ``linregress``
        returns ``p_value == nan``, which would bypass the significance gate).
        """
        form_x: list[float] = []
        form_y: list[float] = []
        for activity, ordinal in zip(activities, ordinals, strict=True):
            gct_fade = activity.get("gct_fade_pct")
            if gct_fade is not None:
                form_x.append(float(ordinal - base))
                form_y.append(float(gct_fade))

        if len(form_y) < 3:
            return None, "insufficient_data"

        slope, _intercept, _r, p_value, _std_err = stats.linregress(
            np.array(form_x, dtype=float), form_y
        )

        if p_value > _P_VALUE_THRESHOLD:
            form_direction = "stable"
        elif slope < 0:
            form_direction = "improving"  # form fade falling = better durability
        else:
            form_direction = "worsening"

        return float(slope), form_direction

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
