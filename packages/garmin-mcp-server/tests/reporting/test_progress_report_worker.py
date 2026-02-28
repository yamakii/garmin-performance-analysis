"""Tests for ProgressReportWorker."""

import pytest

from garmin_mcp.reporting.progress_report_worker import ProgressReportWorker


def _make_activity(
    date: str,
    distance_km: float = 7.0,
    avg_pace: float = 405.0,
    avg_hr: float | None = 145.0,
    zone2_pct: float | None = 40.0,
    form_score: float | None = 85.0,
    cadence: float | None = 175.0,
) -> dict:
    return {
        "date": date,
        "distance_km": distance_km,
        "avg_pace_seconds_per_km": avg_pace,
        "avg_hr": avg_hr,
        "zone2_pct": zone2_pct,
        "form_score": form_score,
        "cadence": cadence,
        "training_type": "aerobic_base",
    }


def _make_4_weeks_activities() -> list[dict]:
    """Create 4 weeks of activities with improving trends."""
    return [
        # Week 1 (2025-10-06 Mon ~ 2025-10-12 Sun)
        _make_activity("2025-10-06", 10.0, 405.0, 150.0, 35.0, 85.0),
        _make_activity("2025-10-08", 7.0, 410.0, 148.0, 33.0, 84.0),
        _make_activity("2025-10-10", 15.0, 400.0, 152.0, 37.0, 86.0),
        # Week 2 (2025-10-13 ~ 2025-10-19)
        _make_activity("2025-10-13", 10.0, 400.0, 147.0, 40.0, 87.0),
        _make_activity("2025-10-15", 8.0, 395.0, 145.0, 44.0, 88.0),
        _make_activity("2025-10-17", 17.0, 405.0, 149.0, 42.0, 88.0),
        # Week 3 (2025-10-20 ~ 2025-10-26)
        _make_activity("2025-10-20", 12.0, 395.0, 144.0, 46.0, 89.0),
        _make_activity("2025-10-22", 8.0, 390.0, 142.0, 50.0, 90.0),
        _make_activity("2025-10-24", 18.0, 398.0, 146.0, 48.0, 89.0),
        # Week 4 (2025-10-27 ~ 2025-11-02)
        _make_activity("2025-10-27", 10.0, 393.0, 143.0, 44.0, 91.0),
        _make_activity("2025-10-29", 8.0, 388.0, 140.0, 48.0, 91.5),
        _make_activity("2025-10-31", 18.0, 395.0, 145.0, 43.0, 90.5),
    ]


@pytest.mark.unit
class TestProgressReportWorker:
    """Unit tests for ProgressReportWorker."""

    def test_generate_weekly_report_structure(self) -> None:
        """Mock 4 weeks of data -> weeks array has 4 items."""
        worker = ProgressReportWorker()
        activities = _make_4_weeks_activities()

        result = worker.generate(
            activities,
            start_date="2025-10-01",
            end_date="2025-10-31",
            period="weekly",
        )

        assert "weeks" in result
        assert len(result["weeks"]) == 4
        assert "trends" in result
        assert result["total_activities"] == 12

        # Each week should have required fields
        for week in result["weeks"]:
            assert "label" in week
            assert "total_distance_km" in week
            assert "avg_pace_formatted" in week
            assert "run_count" in week

    def test_generate_with_empty_period(self) -> None:
        """0 activities -> no error, empty report."""
        worker = ProgressReportWorker()

        result = worker.generate(
            activities=[],
            start_date="2025-10-01",
            end_date="2025-10-31",
            period="weekly",
        )

        assert result["weeks"] == []
        assert result["trends"] == {}
        assert result["total_activities"] == 0

    def test_generate_calculates_trends(self) -> None:
        """Mock 4 weeks with improving pace -> trends.pace_change < 0."""
        worker = ProgressReportWorker()
        activities = _make_4_weeks_activities()

        result = worker.generate(
            activities,
            start_date="2025-10-01",
            end_date="2025-10-31",
        )

        trends = result["trends"]
        # Activities have decreasing pace values (improving)
        assert "pace_change" in trends
        assert (
            trends["pace_change"] < 0
        ), f"Expected pace improvement (negative change), got {trends['pace_change']}"

    def test_aggregate_weekly_grouping(self) -> None:
        """14 days of activities -> 2 weeks correctly grouped."""
        worker = ProgressReportWorker()
        activities = [
            # Week 1 (2025-10-06 Mon ~ 2025-10-12 Sun, ISO week 41)
            _make_activity("2025-10-06", 5.0),
            _make_activity("2025-10-08", 7.0),
            _make_activity("2025-10-10", 10.0),
            # Week 2 (2025-10-13 Mon ~ 2025-10-19 Sun, ISO week 42)
            _make_activity("2025-10-13", 6.0),
            _make_activity("2025-10-15", 8.0),
        ]

        weeks = worker._aggregate_weekly(activities)

        assert len(weeks) == 2
        assert weeks[0]["run_count"] == 3
        assert weeks[1]["run_count"] == 2
        assert weeks[0]["label"] == "W1"
        assert weeks[1]["label"] == "W2"

    def test_aggregate_weekly_metrics(self) -> None:
        """1 week with 3 runs (6:30, 6:40, 6:50/km) -> accurate avg pace."""
        worker = ProgressReportWorker()
        # All same distance for simple average
        activities = [
            _make_activity("2025-10-06", 7.0, 390.0),  # 6:30/km
            _make_activity("2025-10-08", 7.0, 400.0),  # 6:40/km
            _make_activity("2025-10-10", 7.0, 410.0),  # 6:50/km
        ]

        weeks = worker._aggregate_weekly(activities)

        assert len(weeks) == 1
        # Equal distances -> simple average: (390+400+410)/3 = 400.0
        assert weeks[0]["avg_pace_seconds_per_km"] == 400.0
        assert weeks[0]["avg_pace_formatted"] == "6:40/km"
        assert weeks[0]["total_distance_km"] == 21.0

    def test_format_pace_static(self) -> None:
        """Static method formats pace correctly."""
        assert ProgressReportWorker._format_pace(400.0) == "6:40/km"
        assert ProgressReportWorker._format_pace(330.0) == "5:30/km"
        assert ProgressReportWorker._format_pace(270.0) == "4:30/km"

    def test_render_produces_markdown(self) -> None:
        """Render produces markdown with table and trends."""
        worker = ProgressReportWorker()
        activities = _make_4_weeks_activities()

        markdown = worker.render(
            activities,
            start_date="2025-10-01",
            end_date="2025-10-31",
        )

        assert "プログレスレポート" in markdown
        assert "W1" in markdown
        assert "W4" in markdown
        assert "トレンド" in markdown
        assert "平均ペース" in markdown

    def test_render_empty_activities(self) -> None:
        """Render with no activities produces empty-state message."""
        worker = ProgressReportWorker()

        markdown = worker.render(
            activities=[],
            start_date="2025-10-01",
            end_date="2025-10-31",
        )

        assert "アクティビティがありません" in markdown

    def test_single_week_no_trends(self) -> None:
        """Single week produces no trends (need at least 2 weeks)."""
        worker = ProgressReportWorker()
        activities = [
            _make_activity("2025-10-06", 7.0),
            _make_activity("2025-10-08", 10.0),
        ]

        result = worker.generate(
            activities,
            start_date="2025-10-06",
            end_date="2025-10-12",
        )

        assert len(result["weeks"]) == 1
        assert result["trends"] == {}

    def test_weighted_average_pace(self) -> None:
        """Pace is weighted by distance, not simple average."""
        worker = ProgressReportWorker()
        activities = [
            # Short run at fast pace
            _make_activity("2025-10-06", 3.0, 300.0),  # 5:00/km, 3km
            # Long run at slow pace
            _make_activity("2025-10-08", 12.0, 420.0),  # 7:00/km, 12km
        ]

        weeks = worker._aggregate_weekly(activities)

        # Weighted: (300*3 + 420*12) / (3+12) = (900+5040)/15 = 396.0
        assert weeks[0]["avg_pace_seconds_per_km"] == 396.0

    def test_none_metrics_handled(self) -> None:
        """Activities with None metrics don't cause errors."""
        worker = ProgressReportWorker()
        activities = [
            _make_activity(
                "2025-10-06",
                avg_hr=None,
                zone2_pct=None,
                form_score=None,
                cadence=None,
            ),
            _make_activity(
                "2025-10-08",
                avg_hr=None,
                zone2_pct=None,
                form_score=None,
                cadence=None,
            ),
        ]

        result = worker.generate(
            activities,
            start_date="2025-10-06",
            end_date="2025-10-12",
        )

        week = result["weeks"][0]
        assert week["avg_hr"] is None
        assert week["avg_zone2_pct"] is None
        assert week["avg_form_score"] is None
