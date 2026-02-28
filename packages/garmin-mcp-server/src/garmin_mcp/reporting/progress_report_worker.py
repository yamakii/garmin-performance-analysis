"""Generate weekly/monthly progress reports."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


class ProgressReportWorker:
    """Generate weekly/monthly progress reports.

    Aggregates activity data into weekly periods and calculates
    trends for pace, zone distribution, form scores, and volume.
    """

    def generate(
        self,
        activities: list[dict[str, Any]],
        start_date: str,
        end_date: str,
        period: str = "weekly",
    ) -> dict[str, Any]:
        """Generate progress report for given date range.

        Args:
            activities: List of activity dicts with keys:
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km,
                avg_heart_rate, zone2_percentage, integrated_score
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            period: Aggregation period ("weekly" or "monthly").

        Returns:
            Dict with "weeks" list and "trends" dict.
        """
        if not activities:
            return {
                "weeks": [],
                "trends": {},
                "start_date": start_date,
                "end_date": end_date,
            }

        if period == "weekly":
            weeks = self._aggregate_weekly(activities)
        else:
            weeks = self._aggregate_weekly(activities)  # TODO: monthly aggregation

        trends = self._calculate_trends(weeks)

        return {
            "weeks": weeks,
            "trends": trends,
            "start_date": start_date,
            "end_date": end_date,
        }

    def _aggregate_weekly(
        self, activities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Group activities by ISO week and aggregate metrics.

        Args:
            activities: List of activity dicts.

        Returns:
            List of weekly summary dicts, sorted by week.
        """
        # Group by ISO week
        week_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for act in activities:
            act_date = act["activity_date"]
            if isinstance(act_date, str):
                act_date = date.fromisoformat(act_date)
            iso_year, iso_week, _ = act_date.isocalendar()
            key = (iso_year, iso_week)
            if key not in week_groups:
                week_groups[key] = []
            week_groups[key].append(act)

        # Aggregate each week
        weeks = []
        for key in sorted(week_groups):
            group = week_groups[key]
            iso_year, iso_week = key

            total_distance = sum(a["total_distance_km"] for a in group)
            total_time = sum(a["total_time_seconds"] for a in group)

            # Distance-weighted average pace
            avg_pace = total_time / total_distance if total_distance > 0 else 0.0

            # Simple averages for zone2 and form score
            zone2_values = [
                a["zone2_percentage"]
                for a in group
                if a.get("zone2_percentage") is not None
            ]
            form_values = [
                a["integrated_score"]
                for a in group
                if a.get("integrated_score") is not None
            ]

            avg_zone2 = sum(zone2_values) / len(zone2_values) if zone2_values else 0.0
            avg_form = sum(form_values) / len(form_values) if form_values else 0.0

            # Week start date (Monday)
            week_start = date.fromisocalendar(iso_year, iso_week, 1)

            weeks.append(
                {
                    "week_label": f"W{iso_week}",
                    "week_start": str(week_start),
                    "num_activities": len(group),
                    "distance_km": round(total_distance, 1),
                    "total_time_seconds": total_time,
                    "avg_pace_sec_per_km": round(avg_pace, 1),
                    "zone2_pct": round(avg_zone2, 1),
                    "form_score": round(avg_form, 1),
                }
            )

        return weeks

    def _calculate_trends(self, weeks: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate trends between first and last week.

        Args:
            weeks: List of weekly summary dicts.

        Returns:
            Dict with trend metrics (negative pace_change = improvement).
        """
        if len(weeks) < 2:
            return {}

        first = weeks[0]
        last = weeks[-1]

        pace_change = last["avg_pace_sec_per_km"] - first["avg_pace_sec_per_km"]
        zone2_change = last["zone2_pct"] - first["zone2_pct"]
        form_change = last["form_score"] - first["form_score"]

        return {
            "pace_change": round(pace_change, 1),
            "zone2_change": round(zone2_change, 1),
            "form_change": round(form_change, 1),
        }

    def render(
        self,
        activities: list[dict[str, Any]],
        start_date: str,
        end_date: str,
        period: str = "weekly",
    ) -> str:
        """Generate and render progress report as markdown.

        Args:
            activities: List of activity dicts.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            period: Aggregation period ("weekly" or "monthly").

        Returns:
            Rendered markdown string.
        """
        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        data = self.generate(
            activities=activities,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )

        # Add formatted pace to each week
        for week in data["weeks"]:
            week["avg_pace_formatted"] = self._format_pace(week["avg_pace_sec_per_km"])

        num_weeks = len(data["weeks"])
        title = f"{num_weeks}週間プログレスレポート"

        template_dir = str(Path(__file__).parent / "templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("progress_report.j2")

        return template.render(
            title=title,
            start_date=start_date,
            end_date=end_date,
            weeks=data["weeks"],
            trends=data.get("trends", {}),
        )

    @staticmethod
    def _format_pace(seconds_per_km: float) -> str:
        """Format pace as M:SS/km.

        Args:
            seconds_per_km: Pace in seconds per kilometer.

        Returns:
            Formatted string like "6:45/km".
        """
        minutes = int(seconds_per_km // 60)
        secs = int(seconds_per_km % 60)
        return f"{minutes}:{secs:02d}/km"
