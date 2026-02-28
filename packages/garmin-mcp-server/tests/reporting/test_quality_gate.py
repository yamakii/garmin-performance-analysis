"""Tests for advisory quality gate."""

from typing import Any
from unittest.mock import patch

import pytest

from garmin_mcp.reporting.quality_gate import QualityGate


@pytest.mark.unit
class TestZoneContradiction:
    """Tests for zone contradiction detection."""

    def test_detect_zone_contradiction(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "Zone 2が不足しているが、理想的配分に近い走りができた"
            }
        }
        warnings = gate.check_zone_contradiction(section_analyses)
        assert len(warnings) == 1
        assert "Zone contradiction" in warnings[0]

    def test_no_zone_contradiction(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "Zone 2が80%を占め、理想的配分で効率的な走り"}
        }
        warnings = gate.check_zone_contradiction(section_analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestSingleAction:
    """Tests for single action check."""

    def test_detect_multiple_actions(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回はHR 135-140bpmを維持",
                    "次回はペース5:30/kmで走る",
                ]
            }
        }
        warnings = gate.check_single_action(section_analyses)
        assert len(warnings) == 1
        assert "Multiple next actions" in warnings[0]

    def test_single_action_passes(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回はHR 135-140bpmを維持",
                    "フォーム改善のポイント",
                ]
            }
        }
        warnings = gate.check_single_action(section_analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestNumericAction:
    """Tests for numeric action check."""

    def test_detect_no_numeric_action(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回はもっとゆっくり走りましょう",
                ]
            }
        }
        warnings = gate.check_numeric_action(section_analyses)
        assert len(warnings) == 1
        assert "Non-numeric" in warnings[0]

    def test_numeric_action_passes(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回はHR 135-140bpmを維持",
                ]
            }
        }
        warnings = gate.check_numeric_action(section_analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestSuccessCriterion:
    """Tests for success criterion check."""

    def test_detect_missing_success_criterion(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回はHR 135-140bpmを維持する",
                ]
            }
        }
        warnings = gate.check_success_criterion(section_analyses)
        assert len(warnings) == 1
        assert "Missing success criterion" in warnings[0]

    def test_success_criterion_passes(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "recommendations": [
                    "次回Zone 2が60%超なら成功と判定",
                ]
            }
        }
        warnings = gate.check_success_criterion(section_analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestValidate:
    """Tests for the aggregate validate method."""

    def test_all_checks_pass(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "Zone 2が80%を占め、効率的な走り"},
            "summary": {
                "recommendations": [
                    "次回Zone 2が60%超なら成功と判定。HR 135bpm目標",
                ]
            },
        }
        result = gate.validate(section_analyses)
        assert result.passed is True
        assert result.warnings == []

    def test_multiple_warnings(self) -> None:
        gate = QualityGate()
        section_analyses: dict[str, dict[str, Any]] = {
            "efficiency": {"evaluation": "Zone 2が不足しているが、理想的配分だった"},
            "summary": {
                "recommendations": [
                    "次回はもっとゆっくり走りましょう",
                    "次回はフォームを意識しましょう",
                ]
            },
        }
        result = gate.validate(section_analyses)
        assert result.passed is False
        assert len(result.warnings) >= 2


@pytest.mark.integration
class TestQualityGateIntegration:
    """Integration test for quality gate in report pipeline."""

    def test_e2e_quality_gate_in_report(self) -> None:
        with patch(
            "garmin_mcp.reporting.report_generator_worker.ReportGeneratorWorker.__init__",
            return_value=None,
        ):
            from garmin_mcp.reporting.report_generator_worker import (
                ReportGeneratorWorker,
            )

            worker = ReportGeneratorWorker.__new__(ReportGeneratorWorker)
            worker._quality_gate = QualityGate()

            section_analyses: dict[str, dict[str, Any]] = {
                "efficiency": {"evaluation": "Zone 2不足だが理想的配分"},
                "summary": {
                    "recommendations": [
                        "次回はもっと頑張りましょう",
                    ]
                },
            }

            result = worker._quality_gate.validate(section_analyses)
            assert result.passed is False
            assert len(result.warnings) >= 1
