"""
Unit tests for ReportGeneratorWorker.

TDD Red phase: All tests should fail initially.
"""

from typing import Any

from tools.reporting.report_generator_worker import ReportGeneratorWorker
from tools.reporting.report_template_renderer import ReportTemplateRenderer


class TestReportGeneratorWorker:
    """Test ReportGeneratorWorker data loading methods."""

    def test_load_performance_data_success(self):
        """DuckDBからperformance dataを正しく読み取れることを確認."""
        worker = ReportGeneratorWorker(":memory:")

        # Setup: Insert test activity
        # TODO: Setup test data in database

        data = worker.load_performance_data(12345)

        assert data is not None
        assert "basic_metrics" in data
        assert data["basic_metrics"]["distance_km"] > 0

    def test_load_section_analyses_all_sections(self):
        """5つのセクション分析を正しく取得できることを確認."""
        worker = ReportGeneratorWorker(":memory:")

        # Setup: Insert 5 section analyses
        # TODO: Setup test data in database

        analyses = worker.load_section_analyses(12345)

        assert analyses is not None
        assert "efficiency" in analyses
        assert "environment_analysis" in analyses
        assert "phase_evaluation" in analyses
        assert "split_analysis" in analyses
        assert "summary" in analyses

    def test_load_section_analyses_includes_gear(self):
        """Environment分析にgear情報が含まれることを確認."""
        worker = ReportGeneratorWorker(":memory:")

        # Setup: Insert environment section with gear info
        # TODO: Setup test data in database

        analyses = worker.load_section_analyses(12345)

        assert analyses is not None
        assert "environment_analysis" in analyses
        env = analyses["environment_analysis"]
        assert "gear" in env
        assert "shoes" in env["gear"]


class TestReportTemplateRenderer:
    """Test ReportTemplateRenderer JSON data handling."""

    def test_renderer_accepts_json_data(self):
        """RendererがJSON dataを受け取ってレンダリングできることを確認."""
        renderer = ReportTemplateRenderer()

        basic_metrics = {
            "distance_km": 5.0,
            "duration_seconds": 1800,
            "avg_pace_seconds_per_km": 360,
            "avg_heart_rate": 155,
        }

        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "form_efficiency": "GCT: 262ms",
                "hr_efficiency": "Zone 1優位",
            },
            "environment_analysis": {
                "weather_conditions": "気温18.0°C",
                "gear": {"shoes": "Nike Vaporfly"},
            },
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        report = renderer.render_report(
            "12345", "2025-09-22", basic_metrics, section_analyses
        )

        assert "5.0" in report or "5.00" in report  # Template側でフォーマット
        assert "GCT: 262ms" in report
        assert "Nike Vaporfly" in report

    def test_renderer_handles_missing_sections(self):
        """空のセクションに対してTemplate側で適切に処理されることを確認."""
        renderer = ReportTemplateRenderer()

        basic_metrics = {"distance_km": 5.0, "duration_seconds": 1800}
        section_analyses = {
            "efficiency": {"form_efficiency": "GCT: 262ms"},
            "environment_analysis": {},  # 空セクション
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        report = renderer.render_report(
            "12345", "2025-09-22", basic_metrics, section_analyses
        )

        assert report is not None
        # Template側で空セクションの扱いを実装
        # （例: 「データなし」メッセージ、またはセクション非表示）
