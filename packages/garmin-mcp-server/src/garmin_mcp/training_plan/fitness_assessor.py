"""Fitness assessment from recent training data.

Queries DuckDB to evaluate current fitness level, VDOT, pace zones,
training volume, and training type distribution.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.training_plan.models import FitnessSummary, HRZones
from garmin_mcp.training_plan.vdot import VDOTCalculator

logger = logging.getLogger(__name__)


class FitnessAssessor(BaseDBReader):
    """Assesses current fitness level from recent training data."""

    def assess(self, lookback_weeks: int = 8) -> FitnessSummary:
        """Assess current fitness from recent training history.

        Args:
            lookback_weeks: Number of weeks to analyze (default: 8).

        Returns:
            FitnessSummary with VDOT, pace zones, volume metrics, and gap info.

        Raises:
            ValueError: If no running activities found.
        """
        cutoff_date = datetime.now() - timedelta(weeks=lookback_weeks)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            # 1. Get running activities in lookback period
            rows = conn.execute(
                """
                SELECT activity_id, activity_date, total_distance_km,
                       total_time_seconds, avg_pace_seconds_per_km
                FROM activities
                WHERE activity_date >= ?
                ORDER BY activity_date DESC
                """,
                [cutoff_str],
            ).fetchall()

            if not rows:
                raise ValueError(
                    f"No running activities found in last {lookback_weeks} weeks"
                )

            total_distance = sum(r[2] or 0 for r in rows)
            num_runs = len(rows)
            weekly_volume_km = round(total_distance / lookback_weeks, 1)
            runs_per_week = round(num_runs / lookback_weeks, 1)

            # 2. Detect training gap (7+ days between activities)
            gap_detected = False
            gap_weeks = 0
            gap_end_date_str: str | None = None
            pre_gap_weekly_volume_km = 0.0
            pre_gap_vdot: float | None = None
            recent_runs: list[dict[str, float | str | None]] = []

            def _to_date_str(val: object) -> str:
                """Convert date-like value to YYYY-MM-DD string."""
                if isinstance(val, date):
                    return val.strftime("%Y-%m-%d")
                return str(val)

            def _to_date(val: object) -> date:
                """Convert date-like value to date object."""
                if isinstance(val, date):
                    return val
                return datetime.strptime(str(val), "%Y-%m-%d").date()

            # rows are sorted DESC, so reverse for chronological order
            sorted_rows = sorted(rows, key=lambda r: r[1])
            for i in range(1, len(sorted_rows)):
                prev_d = _to_date(sorted_rows[i - 1][1])
                curr_d = _to_date(sorted_rows[i][1])
                gap_days = (curr_d - prev_d).days
                if gap_days >= 7 and gap_days > gap_weeks * 7:
                    gap_detected = True
                    gap_weeks = gap_days // 7
                    gap_end_date_str = _to_date_str(sorted_rows[i][1])

            if gap_detected and gap_end_date_str is not None:
                # Pre-gap baseline: use wider lookback (24 weeks) to capture
                # sufficient training history before the gap.
                # The standard lookback_weeks may be too narrow when the gap
                # occupies most of the window.
                baseline_cutoff_str = (datetime.now() - timedelta(weeks=24)).strftime(
                    "%Y-%m-%d"
                )

                baseline_rows = conn.execute(
                    """
                    SELECT activity_id, activity_date, total_distance_km,
                           total_time_seconds, avg_pace_seconds_per_km
                    FROM activities
                    WHERE activity_date >= ? AND activity_date < ?
                    ORDER BY activity_date
                    """,
                    [baseline_cutoff_str, gap_end_date_str],
                ).fetchall()

                if baseline_rows:
                    # Aggregate distance per ISO week, then take median
                    weekly_volumes: dict[tuple[int, int], float] = {}
                    for r in baseline_rows:
                        d = _to_date(r[1])
                        week_key = d.isocalendar()[:2]
                        weekly_volumes[week_key] = weekly_volumes.get(week_key, 0) + (
                            r[2] or 0
                        )
                    if weekly_volumes:
                        sorted_vols = sorted(weekly_volumes.values())
                        mid = len(sorted_vols) // 2
                        if len(sorted_vols) % 2 == 0:
                            pre_gap_weekly_volume_km = round(
                                (sorted_vols[mid - 1] + sorted_vols[mid]) / 2, 1
                            )
                        else:
                            pre_gap_weekly_volume_km = round(sorted_vols[mid], 1)

                # Post-gap runs (after the gap)
                post_gap_rows = [
                    r for r in sorted_rows if _to_date_str(r[1]) >= gap_end_date_str
                ]
                for r in post_gap_rows:
                    recent_runs.append(
                        {
                            "date": _to_date_str(r[1]),
                            "distance_km": round(r[2], 2) if r[2] else 0,
                            "pace": round(r[4], 1) if r[4] else None,
                        }
                    )

            # 3. Get latest VO2max
            vo2_row = conn.execute(
                """
                SELECT v.precise_value
                FROM vo2_max v
                JOIN activities a ON v.activity_id = a.activity_id
                WHERE a.activity_date >= ?
                ORDER BY a.activity_date DESC
                LIMIT 1
                """,
                [cutoff_str],
            ).fetchone()
            latest_vo2max = float(vo2_row[0]) if vo2_row else None

            # 5. Calculate VDOT
            if latest_vo2max is not None:
                vdot = VDOTCalculator.vdot_from_vo2max(latest_vo2max)
            else:
                # Use best recent performance (fastest pace with distance >= 3km)
                best = min(
                    (r for r in rows if r[2] and r[2] >= 3.0 and r[3]),
                    key=lambda r: r[4] or float("inf"),
                    default=None,
                )
                if best is None:
                    raise ValueError("No suitable activities for VDOT estimation")
                vdot = VDOTCalculator.vdot_from_race(best[2], best[3])

            # 5b. Pre-gap VDOT (from VO2max before gap, using wider lookback)
            if gap_detected and gap_end_date_str is not None:
                pre_gap_vo2 = conn.execute(
                    """
                    SELECT v.precise_value
                    FROM vo2_max v
                    JOIN activities a ON v.activity_id = a.activity_id
                    WHERE a.activity_date >= ? AND a.activity_date < ?
                    ORDER BY a.activity_date DESC
                    LIMIT 1
                    """,
                    [baseline_cutoff_str, gap_end_date_str],
                ).fetchone()
                if pre_gap_vo2:
                    pre_gap_vdot = round(
                        VDOTCalculator.vdot_from_vo2max(float(pre_gap_vo2[0])), 1
                    )

            # 6. Derive pace zones
            pace_zones = VDOTCalculator.pace_zones(vdot)

            # 7. Derive HR zones from Garmin user settings (DuckDB)
            hr_zones = None
            hz_rows = conn.execute(
                """
                SELECT zone_number, zone_low_boundary, zone_high_boundary
                FROM heart_rate_zones
                WHERE activity_id = (
                    SELECT activity_id FROM activities
                    WHERE activity_date >= ?
                    ORDER BY activity_date DESC
                    LIMIT 1
                )
                ORDER BY zone_number
                """,
                [cutoff_str],
            ).fetchall()
            if len(hz_rows) == 5:
                hr_zones = HRZones(
                    zone1_low=hz_rows[0][1],
                    zone1_high=hz_rows[0][2],
                    zone2_low=hz_rows[1][1],
                    zone2_high=hz_rows[1][2],
                    zone3_low=hz_rows[2][1],
                    zone3_high=hz_rows[2][2],
                    zone4_low=hz_rows[3][1],
                    zone4_high=hz_rows[3][2],
                    zone5_low=hz_rows[4][1],
                    zone5_high=hz_rows[4][2],
                )

            # 8. Training type distribution
            type_rows = conn.execute(
                """
                SELECT training_type, COUNT(*) as cnt
                FROM hr_efficiency
                WHERE activity_id IN (
                    SELECT activity_id FROM activities
                    WHERE activity_date >= ?
                )
                GROUP BY training_type
                """,
                [cutoff_str],
            ).fetchall()

            total_typed = sum(r[1] for r in type_rows) if type_rows else 1
            training_dist = (
                {r[0]: round(r[1] / total_typed, 2) for r in type_rows}
                if type_rows
                else {}
            )

            return FitnessSummary(
                vdot=round(vdot, 1),
                pace_zones=pace_zones,
                hr_zones=hr_zones,
                weekly_volume_km=weekly_volume_km,
                runs_per_week=runs_per_week,
                training_type_distribution=training_dist,
                strengths=[],
                weaknesses=[],
                gap_detected=gap_detected,
                gap_weeks=gap_weeks,
                pre_gap_weekly_volume_km=pre_gap_weekly_volume_km,
                pre_gap_vdot=pre_gap_vdot,
                recent_runs=recent_runs,
            )
