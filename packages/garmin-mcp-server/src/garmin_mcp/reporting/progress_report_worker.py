"""
Progress Report Worker

Generates weekly/monthly progress reports from activity data.
"""

import logging
from datetime import date, datetime
from typing import Any

from garmin_mcp.reporting.components.formatting import format_pace
from garmin_mcp.reporting.report_template_renderer import ReportTemplateRenderer

logger = logging.getLogger(__name__)


class ProgressReportWorker:
    """Generate weekly/monthly progress reports."""

    def __init__(self, renderer: ReportTemplateRenderer | None = None):
        """Initialize progress report worker.

        Args:
            renderer: Template renderer instance (default: creates new one)
        """
        self.renderer = renderer or ReportTemplateRenderer()

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
                - date (str): YYYY-MM-DD
                - distance_km (float): Distance in km
                - avg_pace_seconds_per_km (float): Average pace
                - avg_hr (float | None): Average heart rate
                - zone2_pct (float | None): Zone 2 percentage (0-100)
                - form_score (float | None): Form efficiency score
                - cadence (float | None): Average cadence
                - training_type (str | None): Training type
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Report period ("weekly" or "monthly")

        Returns:
            Report data dict with keys: weeks, trends, start_date, end_date, period
        """
        weeks = self._aggregate_weekly(activities)
        trends = self._calculate_trends(weeks)

        return {
            "weeks": weeks,
            "trends": trends,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "total_activities": len(activities),
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
            activities: List of activity dicts (see generate() for schema)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Report period ("weekly" or "monthly")

        Returns:
            Rendered markdown report
        """
        from typing import cast

        report_data = self.generate(activities, start_date, end_date, period)
        template = self.renderer.load_template("progress_report.j2")
        return cast(str, template.render(**report_data))

    def _aggregate_weekly(
        self, activities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Group activities by ISO week and aggregate metrics.

        Args:
            activities: List of activity dicts

        Returns:
            List of weekly aggregation dicts, sorted by week number
        """
        if not activities:
            return []

        # Group by ISO week
        weekly_groups: dict[str, list[dict[str, Any]]] = {}
        for activity in activities:
            activity_date = self._parse_date(activity["date"])
            iso_year, iso_week, _ = activity_date.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            if week_key not in weekly_groups:
                weekly_groups[week_key] = []
            weekly_groups[week_key].append(activity)

        # Aggregate each week
        weeks = []
        for week_key in sorted(weekly_groups.keys()):
            group = weekly_groups[week_key]
            week_data = self._aggregate_group(group, week_key)
            weeks.append(week_data)

        # Assign sequential labels
        for i, week in enumerate(weeks):
            week["label"] = f"W{i + 1}"

        return weeks

    def _aggregate_group(
        self, activities: list[dict[str, Any]], label: str
    ) -> dict[str, Any]:
        """Aggregate metrics for a group of activities.

        Args:
            activities: Activities in this group
            label: Group label (e.g., "2025-W42")

        Returns:
            Aggregated metrics dict
        """
        total_distance = sum(a.get("distance_km", 0.0) for a in activities)

        # Weighted average pace (weighted by distance)
        pace_sum = 0.0
        distance_sum = 0.0
        for a in activities:
            dist = a.get("distance_km", 0.0)
            pace = a.get("avg_pace_seconds_per_km", 0.0)
            if dist > 0 and pace > 0:
                pace_sum += pace * dist
                distance_sum += dist
        avg_pace = pace_sum / distance_sum if distance_sum > 0 else 0.0

        # Simple averages for other metrics
        zone2_values = [
            a["zone2_pct"] for a in activities if a.get("zone2_pct") is not None
        ]
        form_values = [
            a["form_score"] for a in activities if a.get("form_score") is not None
        ]
        hr_values = [a["avg_hr"] for a in activities if a.get("avg_hr") is not None]
        cadence_values = [
            a["cadence"] for a in activities if a.get("cadence") is not None
        ]

        return {
            "week_key": label,
            "label": label,
            "run_count": len(activities),
            "total_distance_km": round(total_distance, 1),
            "avg_pace_seconds_per_km": round(avg_pace, 1) if avg_pace > 0 else None,
            "avg_pace_formatted": self._format_pace(avg_pace) if avg_pace > 0 else None,
            "avg_zone2_pct": (
                round(sum(zone2_values) / len(zone2_values), 1)
                if zone2_values
                else None
            ),
            "avg_form_score": (
                round(sum(form_values) / len(form_values), 1) if form_values else None
            ),
            "avg_hr": (
                round(sum(hr_values) / len(hr_values), 1) if hr_values else None
            ),
            "avg_cadence": (
                round(sum(cadence_values) / len(cadence_values), 1)
                if cadence_values
                else None
            ),
        }

    def _calculate_trends(self, weeks: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate trends between first and last week.

        Args:
            weeks: Aggregated weekly data (sorted chronologically)

        Returns:
            Trends dict with change values between first and last week
        """
        if len(weeks) < 2:
            return {}

        first = weeks[0]
        last = weeks[-1]

        trends: dict[str, Any] = {}

        # Pace change (negative = improvement)
        if first.get("avg_pace_seconds_per_km") and last.get("avg_pace_seconds_per_km"):
            pace_change = (
                last["avg_pace_seconds_per_km"] - first["avg_pace_seconds_per_km"]
            )
            trends["pace_change"] = round(pace_change, 1)
            trends["pace_change_formatted"] = self._format_pace_change(pace_change)

        # Distance change
        if first.get("total_distance_km") and last.get("total_distance_km"):
            dist_change = last["total_distance_km"] - first["total_distance_km"]
            trends["distance_change_km"] = round(dist_change, 1)

        # Zone 2 change (positive = improvement)
        if (
            first.get("avg_zone2_pct") is not None
            and last.get("avg_zone2_pct") is not None
        ):
            zone2_change = last["avg_zone2_pct"] - first["avg_zone2_pct"]
            trends["zone2_change_pp"] = round(zone2_change, 1)

        # Form score change (positive = improvement)
        if (
            first.get("avg_form_score") is not None
            and last.get("avg_form_score") is not None
        ):
            form_change = last["avg_form_score"] - first["avg_form_score"]
            trends["form_score_change"] = round(form_change, 1)

        # HR change
        if first.get("avg_hr") is not None and last.get("avg_hr") is not None:
            hr_change = last["avg_hr"] - first["avg_hr"]
            trends["hr_change"] = round(hr_change, 1)

        return trends

    @staticmethod
    def _format_pace(seconds_per_km: float) -> str:
        """Format pace as M:SS/km.

        Args:
            seconds_per_km: Pace in seconds per kilometer

        Returns:
            Formatted pace string (e.g., "6:45/km")
        """
        return format_pace(seconds_per_km)

    @staticmethod
    def _format_pace_change(change_seconds: float) -> str:
        """Format pace change with direction indicator.

        Args:
            change_seconds: Change in seconds (negative = faster)

        Returns:
            Formatted change string (e.g., "-10秒/km (改善)")
        """
        sign = "+" if change_seconds >= 0 else ""
        label = "改善" if change_seconds < 0 else "低下"
        return f"{sign}{int(change_seconds)}秒/km ({label})"

    @staticmethod
    def _parse_date(date_str: str) -> date:
        """Parse date string to date object.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            date object
        """
        return datetime.strptime(date_str, "%Y-%m-%d").date()
