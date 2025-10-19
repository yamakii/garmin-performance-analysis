"""Tests for ReportGeneratorWorker path configuration."""

import os
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestReportGeneratorWorkerPaths:
    """Test ReportGeneratorWorker path configuration."""

    def test_report_template_renderer_default_result_path(self):
        """Test that ReportTemplateRenderer uses default result path."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer

        # Ensure no environment variable is set
        with patch.dict(os.environ, {}, clear=True):
            renderer = ReportTemplateRenderer()

            # Get the report path
            report_path = renderer.get_final_report_path("123456", "2025-10-11")

            # Should use default project_root/result
            assert "result/individual" in str(report_path)
            assert report_path.name == "2025-10-11_activity_123456.md"

    def test_report_template_renderer_custom_result_path(self, tmp_path):
        """Test that ReportTemplateRenderer uses custom result path from environment."""
        from tools.reporting.report_template_renderer import ReportTemplateRenderer
        from tools.utils.paths import get_result_dir

        custom_result_dir = tmp_path / "custom_results"
        custom_result_dir.mkdir()

        # Set environment variable
        with patch.dict(os.environ, {"GARMIN_RESULT_DIR": str(custom_result_dir)}):
            # Verify get_result_dir returns custom path
            assert get_result_dir() == custom_result_dir.resolve()

            renderer = ReportTemplateRenderer()

            # Get the report path
            report_path = renderer.get_final_report_path("123456", "2025-10-11")

            # Should use custom result directory
            assert str(report_path).startswith(str(custom_result_dir))
            assert "individual" in str(report_path)
            assert report_path.name == "2025-10-11_activity_123456.md"
