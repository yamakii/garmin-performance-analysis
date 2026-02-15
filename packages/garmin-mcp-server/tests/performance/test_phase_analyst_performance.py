"""
Performance tests for phase-section-analyst training type logic.

Tests verify that training type categorization and phase evaluation
meet performance requirements.
"""

import time
from pathlib import Path

import pytest

from garmin_mcp.database.readers.aggregate import AggregateReader


@pytest.fixture
def db_path():
    """Path to DuckDB database."""
    return (
        Path.home() / "garmin_data" / "data" / "database" / "garmin_performance.duckdb"
    )


@pytest.fixture
def reader(db_path):
    """Aggregate reader for DuckDB queries."""
    return AggregateReader(str(db_path))


@pytest.mark.performance
class TestPhaseEvaluationPerformance:
    """Test performance of phase evaluation with training type awareness."""

    def test_training_type_retrieval_performance(self, reader):
        """Training type retrieval completes in < 300ms."""
        activity_id = 20625808856

        start_time = time.time()
        hr_efficiency = reader.get_hr_efficiency_analysis(activity_id)
        elapsed_ms = (time.time() - start_time) * 1000

        assert hr_efficiency is not None
        assert "training_type" in hr_efficiency
        assert (
            elapsed_ms < 300
        ), f"Training type retrieval took {elapsed_ms:.2f}ms, expected < 300ms"

    def test_performance_trends_retrieval_performance(self, reader):
        """Performance trends retrieval completes in < 300ms."""
        activity_id = 20625808856

        start_time = time.time()
        performance_trends = reader.get_performance_trends(activity_id)
        elapsed_ms = (time.time() - start_time) * 1000

        assert performance_trends is not None
        assert (
            elapsed_ms < 300
        ), f"Performance trends retrieval took {elapsed_ms:.2f}ms, expected < 300ms"

    def test_section_analysis_retrieval_performance(self, reader):
        """Section analysis retrieval completes in < 300ms."""
        activity_id = 20625808856

        start_time = time.time()
        reader.get_section_analysis(activity_id, "phase")
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete quickly regardless of whether analysis exists
        assert (
            elapsed_ms < 300
        ), f"Section analysis retrieval took {elapsed_ms:.2f}ms, expected < 300ms"

    def test_multiple_activities_retrieval_performance(self, reader):
        """Retrieving phase analysis for multiple activities is efficient."""
        activity_ids = [20625808856, 20594901208, 20674329823]

        start_time = time.time()
        for activity_id in activity_ids:
            reader.get_section_analysis(activity_id, "phase")
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in < 900ms for 3 activities (< 300ms per activity)
        assert (
            elapsed_ms < 900
        ), f"Multiple retrievals took {elapsed_ms:.2f}ms, expected < 900ms"


@pytest.mark.performance
class TestTokenEfficiency:
    """Test that training type logic doesn't significantly increase token usage."""

    def test_agent_definition_size(self):
        """Agent definition file size is reasonable."""
        agent_file = Path(".claude/agents/phase-section-analyst.md")

        assert agent_file.exists()

        file_size = agent_file.stat().st_size
        line_count = len(agent_file.read_text(encoding="utf-8").splitlines())

        # Should be under 20KB and under 500 lines
        assert (
            file_size < 20000
        ), f"Agent definition is {file_size} bytes, expected < 20KB"
        assert (
            line_count < 500
        ), f"Agent definition is {line_count} lines, expected < 500"

    def test_evaluation_text_length(self, reader):
        """Evaluation text length is reasonable (not excessively verbose)."""
        activity_id = 20625808856

        analysis = reader.get_section_analysis(activity_id, "phase")

        if analysis:
            # Each evaluation should be 200-1000 characters (2-3 sentences)
            for key in ["warmup_evaluation", "run_evaluation", "cooldown_evaluation"]:
                if key in analysis:
                    eval_text = analysis[key]
                    text_length = len(eval_text)

                    assert (
                        100 < text_length < 2000
                    ), f"{key} is {text_length} chars, expected 100-2000 chars for conciseness"
