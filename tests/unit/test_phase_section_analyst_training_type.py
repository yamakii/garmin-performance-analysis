"""
Unit tests for phase-section-analyst training type categorization.

Tests verify that the agent definition includes training type logic
and properly categorizes training types into low_moderate, tempo_threshold,
and interval_sprint categories.
"""

from pathlib import Path

import pytest


@pytest.fixture
def agent_definition_path():
    """Path to phase-section-analyst agent definition."""
    return Path(".claude/agents/phase-section-analyst.md")


@pytest.fixture
def agent_definition_content(agent_definition_path):
    """Content of phase-section-analyst agent definition."""
    with open(agent_definition_path, encoding="utf-8") as f:
        return f.read()


class TestAgentDefinitionStructure:
    """Test that agent definition has required structure."""

    def test_agent_definition_file_exists(self, agent_definition_path):
        """Agent definition file exists."""
        assert agent_definition_path.exists()

    def test_required_tools_defined(self, agent_definition_content):
        """Agent definition includes all required MCP tools."""
        assert "mcp__garmin-db__get_performance_trends" in agent_definition_content
        assert "mcp__garmin-db__get_hr_efficiency_analysis" in agent_definition_content
        assert (
            "mcp__garmin-db__insert_section_analysis_dict" in agent_definition_content
        )

    def test_training_type_section_exists(self, agent_definition_content):
        """Agent definition includes training type judgment section."""
        assert (
            "## トレーニングタイプ判定" in agent_definition_content
            or "## トレーニングタイプ判定（NEW）" in agent_definition_content
        )


class TestTrainingTypeCategorization:
    """Test that training type categorization is properly defined."""

    def test_low_moderate_category_defined(self, agent_definition_content):
        """Low-moderate category (recovery, aerobic_base) is defined."""
        assert (
            "low_moderate" in agent_definition_content
            or "低～中強度走" in agent_definition_content
        )
        assert "recovery" in agent_definition_content
        assert "aerobic_base" in agent_definition_content

    def test_tempo_threshold_category_defined(self, agent_definition_content):
        """Tempo-threshold category is defined."""
        assert (
            "tempo_threshold" in agent_definition_content
            or "テンポ・閾値走" in agent_definition_content
        )
        assert "tempo" in agent_definition_content
        assert "lactate_threshold" in agent_definition_content

    def test_interval_sprint_category_defined(self, agent_definition_content):
        """Interval-sprint category is defined."""
        assert (
            "interval_sprint" in agent_definition_content
            or "インターバル・スプリント" in agent_definition_content
        )
        assert "vo2max" in agent_definition_content
        assert "anaerobic_capacity" in agent_definition_content
        assert "speed" in agent_definition_content


class TestPhaseRequirements:
    """Test that phase requirements are defined per training type category."""

    def test_low_moderate_phase_requirements(self, agent_definition_content):
        """Low-moderate category has 'not required' phase requirements."""
        # Check for keywords indicating phases are not required
        assert (
            "不要" in agent_definition_content
            or "問題ありません" in agent_definition_content
        )

    def test_tempo_threshold_phase_requirements(self, agent_definition_content):
        """Tempo-threshold category has 'recommended' phase requirements."""
        assert "推奨" in agent_definition_content

    def test_interval_sprint_phase_requirements(self, agent_definition_content):
        """Interval-sprint category has 'required' phase requirements."""
        assert "必須" in agent_definition_content or "警告" in agent_definition_content


class TestEvaluationGuidelines:
    """Test that evaluation guidelines are defined for each category."""

    def test_warmup_evaluation_guidelines_exist(self, agent_definition_content):
        """Warmup evaluation guidelines exist for all categories."""
        assert "ウォームアップ評価" in agent_definition_content

    def test_cooldown_evaluation_guidelines_exist(self, agent_definition_content):
        """Cooldown evaluation guidelines exist for all categories."""
        assert "クールダウン評価" in agent_definition_content

    def test_tone_guidance_exists(self, agent_definition_content):
        """Tone guidance exists for different categories."""
        # Check for tone keywords
        assert (
            "トーン" in agent_definition_content
            or "tone" in agent_definition_content.lower()
        )


class TestSpecialCases:
    """Test that special cases are handled."""

    def test_4_phase_structure_special_case(self, agent_definition_content):
        """4-phase structure (interval training) is handled as interval_sprint."""
        assert "recovery_splits" in agent_definition_content
        assert "4フェーズ" in agent_definition_content

    def test_null_training_type_handling(self, agent_definition_content):
        """Null or unknown training_type has fallback logic."""
        # Check for default/fallback handling
        assert (
            "null" in agent_definition_content.lower()
            or "未知" in agent_definition_content
            or "デフォルト" in agent_definition_content
        )
