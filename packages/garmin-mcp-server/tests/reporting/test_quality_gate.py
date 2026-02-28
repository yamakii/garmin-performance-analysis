"""Unit tests for QualityGate advisory validation."""

import pytest

from garmin_mcp.reporting.quality_gate import QualityGate


@pytest.mark.unit
class TestQualityGate:
    """Test suite for QualityGate."""

    @pytest.fixture
    def gate(self):
        """Create QualityGate instance."""
        return QualityGate()

    # ========== check_zone_contradiction ==========

    def test_detect_zone_contradiction(self, gate):
        """Zone insufficiency + ideal distribution co-existing should warn."""
        sections = {
            "efficiency": {
                "evaluation": "Zone 2の割合が不足しています",
            },
            "summary": {
                "overall": "理想的配分で安定したランニングでした",
            },
        }
        warnings = gate.check_zone_contradiction(sections)
        assert len(warnings) == 1
        assert "矛盾検出" in warnings[0]

    def test_no_zone_contradiction(self, gate):
        """Sufficient zones + ideal distribution should not warn."""
        sections = {
            "efficiency": {
                "evaluation": "Zone 2の配分が適切でした",
            },
            "summary": {
                "overall": "理想的配分で安定したランニングでした",
            },
        }
        warnings = gate.check_zone_contradiction(sections)
        assert len(warnings) == 0

    # ========== check_single_action ==========

    def test_detect_multiple_actions(self, gate):
        """Multiple next actions should warn."""
        sections = {
            "efficiency": {
                "next_action": "HR 135-140 bpmを維持する",
            },
            "summary": {
                "next_action": "ケイデンス180 spmを目指す",
            },
        }
        warnings = gate.check_single_action(sections)
        assert len(warnings) == 1
        assert "2件" in warnings[0]

    def test_single_action_passes(self, gate):
        """Single next action should not warn."""
        sections = {
            "summary": {
                "next_action": "HR 135-140 bpmを維持する",
            },
        }
        warnings = gate.check_single_action(sections)
        assert len(warnings) == 0

    # ========== check_numeric_action ==========

    def test_detect_no_numeric_action(self, gate):
        """Action without numbers should warn."""
        sections = {
            "summary": {
                "next_action": "もっと練習しましょう",
            },
        }
        warnings = gate.check_numeric_action(sections)
        assert len(warnings) == 1
        assert "数値" in warnings[0]

    def test_numeric_action_passes(self, gate):
        """Action with specific numbers should not warn."""
        sections = {
            "summary": {
                "next_action": "次回はHR 135-140 bpmで走る",
            },
        }
        warnings = gate.check_numeric_action(sections)
        assert len(warnings) == 0

    # ========== check_success_criterion ==========

    def test_detect_missing_success_criterion(self, gate):
        """Action without success criterion should warn."""
        sections = {
            "summary": {
                "next_action": "HR 135 bpmで走る",
            },
        }
        warnings = gate.check_success_criterion(sections)
        assert len(warnings) == 1
        assert "成功判定条件" in warnings[0]

    def test_success_criterion_passes(self, gate):
        """Action with success criterion should not warn."""
        sections = {
            "summary": {
                "next_action": "HR 135-140 bpmで走る",
                "success_criterion": "Zone 2が60%超なら成功",
            },
        }
        warnings = gate.check_success_criterion(sections)
        assert len(warnings) == 0

    # ========== validate (integration) ==========

    def test_all_checks_pass(self, gate):
        """All checks passing should return passed=True, empty warnings."""
        sections = {
            "summary": {
                "next_action": "次回Zone 2が60%超なら成功、HR 135-140 bpmを目標に走る",
            },
            "efficiency": {
                "evaluation": "Zone 2の配分が適切でした",
            },
        }
        result = gate.validate(sections)
        assert result["passed"] is True
        assert result["warnings"] == []

    def test_multiple_warnings(self, gate):
        """Multiple failures should collect all warnings."""
        sections = {
            "efficiency": {
                "evaluation": "Zone 2の割合が不足しています",
                "next_action": "もっと頑張りましょう",
            },
            "summary": {
                "overall": "理想的配分で安定したランニングでした",
                "next_action": "ペースを上げましょう",
            },
        }
        result = gate.validate(sections)
        assert result["passed"] is False
        assert len(result["warnings"]) >= 2
