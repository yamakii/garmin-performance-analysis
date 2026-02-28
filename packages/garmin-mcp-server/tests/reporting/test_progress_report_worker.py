"""Tests for ProgressReportWorker."""

from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.mark.unit
class TestProgressReportWorkerGenerate:
    """Tests for ProgressReportWorker.generate()."""

    def _make_activity(
        self,
        activity_id: int,
        activity_date: date,
        distance_km: float,
        pace_sec_per_km: float,
        avg_hr: int,
        zone2_pct: float = 40.0,
        form_score: float = 85.0,
    ) -> dict:
        """Helper to create a mock activity row."""
        total_time = int(pace_sec_per_km * distance_km)
        return {
            "activity_id": activity_id,
            "activity_date": activity_date,
            "total_distance_km": distance_km,
            "total_time_seconds": total_time,
            "avg_pace_seconds_per_km": pace_sec_per_km,
            "avg_heart_rate": avg_hr,
            "zone2_percentage": zone2_pct,
            "integrated_score": form_score,
        }

    def _make_weeks_data(self, num_weeks: int = 4) -> list[dict]:
        """Create mock activity data spanning num_weeks."""
        activities = []
        base_date = date(2025, 10, 1)
        activity_id = 1000

        for week_idx in range(num_weeks):
            for run_idx in range(3):  # 3 runs per week
                day_offset = week_idx * 7 + run_idx * 2
                act_date = base_date + timedelta(days=day_offset)
                pace = 405 - week_idx * 5  # improving pace each week
                form = 85.0 + week_idx * 2.0  # improving form
                zone2 = 35.0 + week_idx * 3.0  # improving zone2
                activities.append(
                    self._make_activity(
                        activity_id=activity_id + week_idx * 10 + run_idx,
                        activity_date=act_date,
                        distance_km=10.0 + run_idx,
                        pace_sec_per_km=pace,
                        avg_hr=145,
                        zone2_pct=zone2,
                        form_score=form,
                    )
                )
        return activities

    def test_generate_weekly_report_structure(self) -> None:
        """Mock 4 weeks data -> weeks array has 4 items, each with required fields."""
        from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

        worker = ProgressReportWorker()
        activities = self._make_weeks_data(num_weeks=4)

        result = worker.generate(
            activities=activities,
            start_date="2025-10-01",
            end_date="2025-10-28",
            period="weekly",
        )

        assert "weeks" in result
        assert len(result["weeks"]) == 4

        for week in result["weeks"]:
            assert "distance_km" in week
            assert "avg_pace_sec_per_km" in week
            assert "zone2_pct" in week
            assert "form_score" in week

    def test_generate_with_empty_period(self) -> None:
        """0 activities -> no error, empty report returned."""
        from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

        worker = ProgressReportWorker()

        result = worker.generate(
            activities=[],
            start_date="2025-10-01",
            end_date="2025-10-28",
            period="weekly",
        )

        assert "weeks" in result
        assert len(result["weeks"]) == 0
        assert "trends" in result

    def test_generate_calculates_trends(self) -> None:
        """Mock 4 weeks data with improving pace -> trends.pace_change < 0."""
        from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

        worker = ProgressReportWorker()
        activities = self._make_weeks_data(num_weeks=4)

        result = worker.generate(
            activities=activities,
            start_date="2025-10-01",
            end_date="2025-10-28",
            period="weekly",
        )

        assert "trends" in result
        trends = result["trends"]
        assert "pace_change" in trends
        assert trends["pace_change"] < 0  # Negative = improvement (faster)


@pytest.mark.unit
class TestProgressReportWorkerAggregateWeekly:
    """Tests for ProgressReportWorker._aggregate_weekly()."""

    def test_aggregate_weekly_grouping(self) -> None:
        """14 days of activities -> grouped into 2 weeks."""
        from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

        worker = ProgressReportWorker()
        base_date = date(2025, 10, 6)  # Monday

        activities = []
        for i in range(14):
            act_date = base_date + timedelta(days=i)
            activities.append(
                {
                    "activity_id": 2000 + i,
                    "activity_date": act_date,
                    "total_distance_km": 10.0,
                    "total_time_seconds": 3600,
                    "avg_pace_seconds_per_km": 360.0,
                    "avg_heart_rate": 140,
                    "zone2_percentage": 45.0,
                    "integrated_score": 88.0,
                }
            )

        weeks = worker._aggregate_weekly(activities)

        assert len(weeks) == 2
        # First week: 7 activities, second week: 7 activities
        assert weeks[0]["num_activities"] == 7
        assert weeks[1]["num_activities"] == 7

    def test_aggregate_weekly_metrics(self) -> None:
        """1 week with 3 runs (6:30, 6:40, 6:50/km) -> avg pace calculated correctly."""
        from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker

        worker = ProgressReportWorker()
        base_date = date(2025, 10, 6)  # Monday

        paces = [390.0, 400.0, 410.0]  # 6:30, 6:40, 6:50 in seconds
        distances = [10.0, 10.0, 10.0]

        activities = []
        for i, (pace, dist) in enumerate(zip(paces, distances, strict=True)):
            activities.append(
                {
                    "activity_id": 3000 + i,
                    "activity_date": base_date + timedelta(days=i * 2),
                    "total_distance_km": dist,
                    "total_time_seconds": int(pace * dist),
                    "avg_pace_seconds_per_km": pace,
                    "avg_heart_rate": 145,
                    "zone2_percentage": 42.0,
                    "integrated_score": 87.0,
                }
            )

        weeks = worker._aggregate_weekly(activities)

        assert len(weeks) == 1
        # Average pace: (390 + 400 + 410) / 3 = 400.0
        assert weeks[0]["avg_pace_sec_per_km"] == pytest.approx(400.0, abs=0.1)
        # Total distance: 30km
        assert weeks[0]["distance_km"] == pytest.approx(30.0, abs=0.1)
