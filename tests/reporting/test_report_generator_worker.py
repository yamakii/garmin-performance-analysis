"""
Unit tests for ReportTemplateRenderer.

Tests JSON data rendering in templates.
"""

from typing import Any

import pytest

from tools.reporting.report_template_renderer import ReportTemplateRenderer


@pytest.mark.unit
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
                "evaluation": "GCT: 262msの優秀な接地時間、Zone 1優位の効率的な心拍管理"
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
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "GCT: 262msの優秀な接地時間"},
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
