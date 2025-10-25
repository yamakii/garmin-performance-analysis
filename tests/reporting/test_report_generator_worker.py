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


@pytest.mark.unit
class TestMermaidGraphGeneration:
    """Test Mermaid graph data generation."""

    def test_mermaid_data_structure(self, mocker):
        """Mermaid dataが正しい構造を持つことを確認."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        # Mock the db_reader to avoid needing a real database
        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        # Create sample splits data
        splits: list[dict[str, Any]] = [
            {
                "index": 1,
                "pace_seconds_per_km": 400,
                "heart_rate": 140,
                "power": 250,
            },
            {
                "index": 2,
                "pace_seconds_per_km": 410,
                "heart_rate": 145,
                "power": 255,
            },
            {
                "index": 3,
                "pace_seconds_per_km": 405,
                "heart_rate": 143,
                "power": None,  # Test None handling
            },
        ]

        mermaid_data = worker._generate_mermaid_data(splits)

        # Check structure
        assert mermaid_data is not None
        assert "x_axis_labels" in mermaid_data
        assert "pace_data" in mermaid_data
        assert "heart_rate_data" in mermaid_data
        assert "power_data" in mermaid_data
        assert "pace_min" in mermaid_data
        assert "pace_max" in mermaid_data
        assert "hr_min" in mermaid_data
        assert "hr_max" in mermaid_data

        # Check data types
        assert isinstance(mermaid_data["x_axis_labels"], list)
        assert isinstance(mermaid_data["pace_data"], list)
        assert isinstance(mermaid_data["heart_rate_data"], list)
        assert isinstance(mermaid_data["power_data"], list)

        # Check list lengths match
        assert len(mermaid_data["x_axis_labels"]) == 3
        assert len(mermaid_data["pace_data"]) == 3
        assert len(mermaid_data["heart_rate_data"]) == 3
        assert len(mermaid_data["power_data"]) == 3

        # Check None power handling (should be 0)
        assert mermaid_data["power_data"][2] == 0

        # Check Y-axis ranges (10% padding)
        assert mermaid_data["pace_min"] == round(400 * 0.9, 1)
        assert mermaid_data["pace_max"] == round(410 * 1.1, 1)
        assert mermaid_data["hr_min"] == round(140 * 0.9, 1)
        assert mermaid_data["hr_max"] == round(145 * 1.1, 1)

    def test_mermaid_data_empty_splits(self, mocker):
        """空のsplitsに対してNoneを返すことを確認."""
        from tools.reporting.report_generator_worker import ReportGeneratorWorker

        # Mock the db_reader to avoid needing a real database
        mock_reader = mocker.Mock()
        worker = ReportGeneratorWorker()
        worker.db_reader = mock_reader

        mermaid_data = worker._generate_mermaid_data([])
        assert mermaid_data is None

        mermaid_data = worker._generate_mermaid_data(None)
        assert mermaid_data is None

    def test_mermaid_graph_renders_in_template(self):
        """Template内でMermaidグラフがレンダリングされることを確認."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        renderer = ReportTemplateRenderer()

        basic_metrics = {
            "distance_km": 5.0,
            "duration_seconds": 1800,
            "avg_pace_seconds_per_km": 360,
            "avg_heart_rate": 155,
        }

        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "Test"},
            "environment_analysis": {},
            "phase_evaluation": {},
            "split_analysis": {},
            "summary": {},
        }

        mermaid_data = {
            "x_axis_labels": ["1", "2", "3"],
            "pace_data": [400, 410, 405],
            "heart_rate_data": [140, 145, 143],
            "power_data": [250, 255, 0],
            "pace_min": 360.0,
            "pace_max": 451.0,
            "hr_min": 126.0,
            "hr_max": 159.5,
        }

        # Test that mermaid_data parameter is accepted (template rendering is separate concern)
        report = renderer.render_report(
            "12345",
            "2025-09-22",
            basic_metrics,
            section_analyses,
            mermaid_data=mermaid_data,
        )

        # Check that report was generated successfully
        assert report is not None
        assert len(report) > 0
        # Note: Actual Mermaid rendering in template is tested in integration tests
