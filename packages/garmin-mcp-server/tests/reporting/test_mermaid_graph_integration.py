"""Integration tests for Mermaid graph in reports.

Tests that Mermaid graphs are properly generated and appear in final reports.
"""

import pytest

from garmin_mcp.reporting.report_generator_worker import ReportGeneratorWorker


class TestMermaidGraphIntegration:
    """Integration test suite for Mermaid graph rendering."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_mermaid_graph_in_report(self):
        """Test that Mermaid graph appears in generated report."""
        worker = ReportGeneratorWorker()
        result = worker.generate_report(activity_id=20625808856)

        with open(result["report_path"]) as f:
            report = f.read()

        # Should have Mermaid graph
        assert "```mermaid" in report
        assert "xychart-beta" in report
        assert "x-axis" in report

        # Should NOT show fallback message
        assert "グラフデータがありません" not in report
