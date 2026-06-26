"""Objective fitness curve DB reader.

Reads every run's splits, applies #558's best-effort segment extraction and
#561's rolling trailing-window max to derive an objective (non-optimistic)
performance-VDOT fitness curve, and places it side-by-side with Garmin's own
VO2max series plus the *optimism gap* (Garmin-derived VDOT minus the objective
VDOT, expressed in VDOT, m/s and s/km).

The pure compute lives in :mod:`garmin_mcp.objective_fitness`; this reader only
wires DuckDB rows into those functions. ``splits.distance`` is stored in
**kilometers** in DuckDB, while :func:`run_best_efforts` expects each split's
``distance`` in **meters**, so distances are multiplied by 1000 before compute
(omitting this silently yields an empty curve, see #565).
"""

from __future__ import annotations

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.objective_fitness import rolling_max_curve, run_best_efforts
from garmin_mcp.training_plan.vdot import VDOTCalculator

logger = logging.getLogger(__name__)

# Reference distance used to translate a VDOT difference into a pace/speed gap.
# 5 km is the canonical benchmark distance and lands the Epic #526 spike gap
# (Garmin 44.6 -> objective ~33-37) at ~0.6 m/s / ~63 s/km.
_GAP_REFERENCE_DISTANCE_KM = 5.0


class FitnessCurveReader(BaseDBReader):
    """Reads the objective fitness curve + Garmin VO2max optimism gap."""

    def get_objective_fitness_curve(
        self,
        window_days: int = 90,
        buckets_km: tuple[float, ...] = (2.0, 5.0, 10.0),
    ) -> dict[str, Any]:
        """Derive the objective fitness curve and the Garmin optimism gap.

        Args:
            window_days: Trailing window (days) for the rolling-max curve.
            buckets_km: Nominal best-effort distance buckets to extract per run.

        Returns:
            Dict with keys:
            - ``objective_curve``: ``[{"date", "vdot", "source_distance_km"}, ...]``
              ascending by run day (empty when no splits exist).
            - ``garmin_vo2max``: ``[{"date", "value"}, ...]`` ascending by date.
            - ``optimism_gap``: ``{"garmin_vdot", "objective_vdot", "gap_vdot",
              "gap_speed_mps", "gap_pace_sec_per_km"}`` or ``None`` when either
              series is empty.
        """
        try:
            with self._get_connection() as conn:
                split_rows = conn.execute("""
                    SELECT a.activity_id, a.activity_date, s.split_index,
                           s.distance, s.duration_seconds
                    FROM splits s
                    JOIN activities a ON a.activity_id = s.activity_id
                    WHERE s.distance IS NOT NULL
                      AND s.duration_seconds IS NOT NULL
                      AND s.duration_seconds > 0
                    ORDER BY a.activity_id, s.split_index
                    """).fetchall()

                garmin_rows = conn.execute("""
                    SELECT date, value
                    FROM vo2_max
                    WHERE value IS NOT NULL AND date IS NOT NULL
                    ORDER BY date
                    """).fetchall()
        except Exception as e:
            logger.error(f"Error reading objective fitness curve: {e}")
            return {
                "objective_curve": [],
                "garmin_vo2max": [],
                "optimism_gap": None,
            }

        objective_curve = self._build_objective_curve(
            split_rows, window_days, buckets_km
        )
        garmin_vo2max = [{"date": str(d), "value": float(v)} for d, v in garmin_rows]
        optimism_gap = self._build_optimism_gap(objective_curve, garmin_vo2max)

        return {
            "objective_curve": objective_curve,
            "garmin_vo2max": garmin_vo2max,
            "optimism_gap": optimism_gap,
        }

    def _build_objective_curve(
        self,
        split_rows: list[tuple[Any, ...]],
        window_days: int,
        buckets_km: tuple[float, ...],
    ) -> list[dict[str, Any]]:
        """Group splits per activity, extract best efforts, roll the max curve."""
        # Group splits by activity (ordered by split_index already from SQL).
        by_activity: dict[int, dict[str, Any]] = {}
        for activity_id, activity_date, split_index, distance, duration in split_rows:
            entry = by_activity.setdefault(
                int(activity_id), {"date": activity_date, "splits": []}
            )
            entry["splits"].append(
                {
                    "split_index": int(split_index),
                    # DuckDB stores distance in km; the pure helper expects meters.
                    "distance": float(distance) * 1000.0,
                    "duration_seconds": float(duration),
                }
            )

        per_run_vdot: list[tuple[str, float, float]] = []
        for entry in by_activity.values():
            run_date = str(entry["date"])
            for effort in run_best_efforts(entry["splits"], buckets_km):
                per_run_vdot.append((run_date, effort.vdot, effort.target_distance_km))

        curve = rolling_max_curve(per_run_vdot, window_days=window_days)
        return [
            {
                "date": point.date,
                "vdot": round(point.vdot, 2),
                "source_distance_km": point.source_distance_km,
            }
            for point in curve
        ]

    def _build_optimism_gap(
        self,
        objective_curve: list[dict[str, Any]],
        garmin_vo2max: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Compare the latest Garmin VDOT against the latest objective VDOT."""
        if not objective_curve or not garmin_vo2max:
            return None

        garmin_vdot = VDOTCalculator.vdot_from_vo2max(garmin_vo2max[-1]["value"])
        objective_vdot = float(objective_curve[-1]["vdot"])

        ref_km = _GAP_REFERENCE_DISTANCE_KM
        garmin_time = VDOTCalculator.predict_race_time(garmin_vdot, ref_km)
        objective_time = VDOTCalculator.predict_race_time(objective_vdot, ref_km)

        garmin_speed = ref_km * 1000.0 / garmin_time
        objective_speed = ref_km * 1000.0 / objective_time

        return {
            "garmin_vdot": round(garmin_vdot, 2),
            "objective_vdot": round(objective_vdot, 2),
            "gap_vdot": round(garmin_vdot - objective_vdot, 2),
            "gap_speed_mps": round(garmin_speed - objective_speed, 3),
            "gap_pace_sec_per_km": round((objective_time - garmin_time) / ref_km, 1),
        }
