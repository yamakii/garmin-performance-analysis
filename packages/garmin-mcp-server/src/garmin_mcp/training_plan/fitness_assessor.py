"""Fitness assessment from recent training data.

Queries DuckDB to evaluate current fitness level, VDOT, pace zones,
training volume, and training type distribution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.training_plan.models import FitnessSummary
from garmin_mcp.training_plan.vdot import VDOTCalculator

logger = logging.getLogger(__name__)


class FitnessAssessor(BaseDBReader):
    """Assesses current fitness level from recent training data."""

    def assess(self, lookback_weeks: int = 8) -> FitnessSummary:
        """Assess current fitness from recent training history.

        Args:
            lookback_weeks: Number of weeks to analyze (default: 8).

        Returns:
            FitnessSummary with VDOT, pace zones, volume metrics.

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
                  AND (activity_name LIKE '%ラン%' OR activity_name LIKE '%Run%')
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

            # 2. Get latest VO2max
            vo2_row = conn.execute(
                """
                SELECT v.precise_value
                FROM vo2_max v
                JOIN activities a ON v.activity_id = a.activity_id
                WHERE a.activity_date >= ?
                  AND (a.activity_name LIKE '%ラン%' OR a.activity_name LIKE '%Run%')
                ORDER BY a.activity_date DESC
                LIMIT 1
                """,
                [cutoff_str],
            ).fetchone()
            latest_vo2max = float(vo2_row[0]) if vo2_row else None

            # 3. Get latest lactate threshold HR
            lt_row = conn.execute(
                """
                SELECT l.heart_rate
                FROM lactate_threshold l
                JOIN activities a ON l.activity_id = a.activity_id
                WHERE a.activity_date >= ?
                  AND (a.activity_name LIKE '%ラン%' OR a.activity_name LIKE '%Run%')
                ORDER BY a.activity_date DESC
                LIMIT 1
                """,
                [cutoff_str],
            ).fetchone()
            lt_hr = int(lt_row[0]) if lt_row else None

            # 4. Calculate VDOT
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

            # 5. Derive pace zones
            pace_zones = VDOTCalculator.pace_zones(vdot)

            # 6. Derive HR zones (if LT available)
            hr_zones = None
            if lt_hr is not None:
                hr_zones = VDOTCalculator.hr_zones_from_lt(lt_hr)

            # 7. Training type distribution
            type_rows = conn.execute(
                """
                SELECT training_type, COUNT(*) as cnt
                FROM hr_efficiency
                WHERE activity_id IN (
                    SELECT activity_id FROM activities
                    WHERE activity_date >= ?
                      AND (activity_name LIKE '%ラン%' OR activity_name LIKE '%Run%')
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
            )
