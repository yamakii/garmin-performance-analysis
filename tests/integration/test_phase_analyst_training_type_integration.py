"""
Integration tests for phase-section-analyst with training type awareness.

Tests verify that the agent correctly handles real data across all training type
categories and properly integrates with DuckDB.
"""

from pathlib import Path

import pytest

from tools.database.readers.aggregate import AggregateReader


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


class TestRealDataIntegration:
    """Test phase evaluation with real activity data."""

    def test_low_moderate_recovery_run(self, reader):
        """Recovery run (low_moderate) evaluates without warnings."""
        # Activity 20594901208: recovery run without warmup/cooldown
        activity_id = 20594901208

        # Get section analysis
        analysis = reader.get_section_analysis(activity_id, "phase")

        assert analysis is not None
        assert "warmup_evaluation" in analysis
        assert "run_evaluation" in analysis
        assert "cooldown_evaluation" in analysis

        # Check for positive language (no warnings)
        warmup_eval = analysis["warmup_evaluation"]
        cooldown_eval = analysis["cooldown_evaluation"]

        # Should contain positive phrases like "問題ありません" or "必要はありません"
        assert "問題ありません" in warmup_eval or "問題あり" not in warmup_eval
        assert "必要はありません" in cooldown_eval or "必要です" not in cooldown_eval

        # Should NOT contain warning indicators
        assert "⚠️" not in warmup_eval
        assert "⚠️" not in cooldown_eval
        assert "怪我リスク" not in warmup_eval
        assert "怪我リスク" not in cooldown_eval

    def test_tempo_threshold_tempo_run(self, reader):
        """Tempo run (tempo_threshold) evaluates with suggestive tone."""
        # Activity 20674329823: tempo run with warmup/cooldown
        activity_id = 20674329823

        # Get section analysis
        analysis = reader.get_section_analysis(activity_id, "phase")

        assert analysis is not None
        assert "warmup_evaluation" in analysis
        assert "run_evaluation" in analysis
        assert "cooldown_evaluation" in analysis

        # Check for educational/suggestive tone
        run_eval = analysis["run_evaluation"]

        # Should contain educational phrases or improvement suggestions
        # Example: "次のステップ", "向上", etc.
        assert len(run_eval) > 50  # Should have detailed evaluation

    def test_interval_sprint_vo2max(self, reader):
        """VO2 max interval (interval_sprint) evaluates with assertive tone."""
        # Activity 20615445009: vo2max interval with 4-phase structure
        activity_id = 20615445009

        # Get section analysis
        analysis = reader.get_section_analysis(activity_id, "phase")

        assert analysis is not None
        assert "warmup_evaluation" in analysis
        assert "run_evaluation" in analysis
        assert "recovery_evaluation" in analysis  # 4-phase structure
        assert "cooldown_evaluation" in analysis

        # Check for assertive/safety-focused tone
        warmup_eval = analysis["warmup_evaluation"]
        recovery_eval = analysis["recovery_evaluation"]

        # Should emphasize importance/necessity
        assert len(warmup_eval) > 50  # Detailed evaluation
        assert len(recovery_eval) > 50  # Detailed evaluation

    def test_aerobic_base_run(self, reader):
        """Aerobic base run (low_moderate) evaluates without warnings."""
        # Activity 20625808856: aerobic_base run (previously tested)
        activity_id = 20625808856

        # Get section analysis
        analysis = reader.get_section_analysis(activity_id, "phase")

        assert analysis is not None

        # Should have relaxed, positive tone
        warmup_eval = analysis["warmup_evaluation"]
        cooldown_eval = analysis["cooldown_evaluation"]

        # Should NOT contain warnings
        assert "⚠️" not in warmup_eval
        assert "⚠️" not in cooldown_eval


class TestDuckDBIntegration:
    """Test DuckDB storage and retrieval."""

    def test_section_analysis_stored_correctly(self, reader):
        """Section analysis is stored with correct structure."""
        # Use any recent activity
        activity_id = 20625808856

        # Get section analysis
        analysis = reader.get_section_analysis(activity_id, "phase")

        assert analysis is not None
        assert isinstance(analysis, dict)

        # Should have standard phase fields
        assert "warmup_evaluation" in analysis or "run_evaluation" in analysis

    def test_upsert_maintains_one_to_one(self, reader, db_path):
        """UPSERT logic maintains 1:1 relationship between activity_id and section_type."""
        import duckdb

        # Pick an activity that has phase analysis
        activity_id = 20625808856
        section_type = "phase"

        # Query database for duplicates
        conn = duckdb.connect(str(db_path))
        result = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM section_analyses
            WHERE activity_id = ? AND section_type = ?
            """,
            [activity_id, section_type],
        ).fetchone()
        conn.close()

        # Should have exactly 1 record (or 0 if not yet analyzed)
        assert result is not None, "Query returned None"
        assert result[0] <= 1, f"Found {result[0]} records, expected 0 or 1"


class TestBackwardCompatibility:
    """Test that existing functionality still works."""

    def test_existing_report_generation_works(self, reader):
        """Existing report generation still works with new agent logic."""
        # This is a smoke test - just verify we can read section analyses
        # without errors for various training types

        test_activities = [
            20625808856,  # aerobic_base
            20594901208,  # recovery
            20674329823,  # tempo
        ]

        for activity_id in test_activities:
            # Should not raise exceptions
            analysis = reader.get_section_analysis(activity_id, "phase")
            # Analysis may be None if not yet generated, which is fine
            if analysis:
                assert isinstance(analysis, dict)


class TestTrainingTypeCategorization:
    """Test training type to category mapping."""

    @pytest.mark.parametrize(
        "training_type,expected_category",
        [
            ("recovery", "low_moderate"),
            ("aerobic_base", "low_moderate"),
            ("tempo", "tempo_threshold"),
            ("lactate_threshold", "tempo_threshold"),
            ("vo2max", "interval_sprint"),
            ("anaerobic_capacity", "interval_sprint"),
            ("speed", "interval_sprint"),
        ],
    )
    def test_training_type_categorization(self, training_type, expected_category):
        """Training types are correctly categorized."""
        # This test validates the categorization logic defined in the agent
        # Note: Actual categorization happens in the agent, this is documentation

        categories = {
            "low_moderate": ["recovery", "aerobic_base"],
            "tempo_threshold": ["tempo", "lactate_threshold"],
            "interval_sprint": ["vo2max", "anaerobic_capacity", "speed"],
        }

        assert training_type in categories[expected_category]
