"""
Tests for QualityGate advisory validation.

Tests cover 5 quality checks and the aggregate validate() method.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.reporting.quality_gate import QualityGate

# =============================================================================
# Unit Tests
# =============================================================================


@pytest.mark.unit
class TestCheckZoneContradiction:
    """Tests for QualityGate.check_zone_contradiction()."""

    def test_detect_zone_contradiction(self) -> None:
        """Zone不足評価 + '理想的配分' テキスト共存 → warning検出."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "Zone 2 不足が見られます",
            },
            "summary": {
                "overall": "理想的な配分で走れています",
            },
        }
        warnings = gate.check_zone_contradiction(analyses)
        assert len(warnings) == 1
        assert warnings[0].check_name == "zone_contradiction"

    def test_no_zone_contradiction(self) -> None:
        """Zone十分評価 + '理想的配分' → warning なし."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "Zone 2 が十分に確保されています",
            },
            "summary": {
                "overall": "理想的な配分で走れています",
            },
        }
        warnings = gate.check_zone_contradiction(analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckSingleAction:
    """Tests for QualityGate.check_single_action()."""

    def test_detect_multiple_actions(self) -> None:
        """next_action に2つ以上のアクション → warning検出."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "next_action": "HR 135-140 bpmを維持。ペースを5:30/kmに保つ",
            },
        }
        warnings = gate.check_single_action(analyses)
        assert len(warnings) == 1
        assert warnings[0].check_name == "multiple_actions"

    def test_single_action_passes(self) -> None:
        """next_action が1つ → warning なし."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "next_action": "HR 135-140 bpmを維持する",
            },
        }
        warnings = gate.check_single_action(analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckNumericAction:
    """Tests for QualityGate.check_numeric_action()."""

    def test_detect_no_numeric_action(self) -> None:
        """next_action='もっと練習しましょう'（数値なし） → warning検出."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "next_action": "もっと練習しましょう",
            },
        }
        warnings = gate.check_numeric_action(analyses)
        assert len(warnings) == 1
        assert warnings[0].check_name == "no_numeric_action"

    def test_numeric_action_passes(self) -> None:
        """next_action='HR 135-140 bpm を維持' → warning なし."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "next_action": "HR 135-140 bpm を維持",
            },
        }
        warnings = gate.check_numeric_action(analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckSuccessCriterion:
    """Tests for QualityGate.check_success_criterion()."""

    def test_detect_missing_success_criterion(self) -> None:
        """success_criterion 未設定 → warning検出."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "next_action": "HR 135 bpmを維持",
            },
        }
        warnings = gate.check_success_criterion(analyses)
        assert len(warnings) == 1
        assert warnings[0].check_name == "missing_success_criterion"

    def test_success_criterion_passes(self) -> None:
        """success_criterion='Zone 2 > 60%' → warning なし."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "summary": {
                "success_criterion": "Zone 2 > 60%",
            },
        }
        warnings = gate.check_success_criterion(analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestValidate:
    """Tests for QualityGate.validate() aggregation."""

    def test_all_checks_pass(self) -> None:
        """全チェック通過 → warnings=[], passed=True."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "Zone 2 が十分に確保されています",
            },
            "summary": {
                "next_action": "HR 135-140 bpmを維持する",
                "success_criterion": "Zone 2 が60%超なら成功",
            },
        }
        result = gate.validate(analyses)
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_multiple_warnings(self) -> None:
        """複数チェック不合格 → 全warning集約."""
        gate = QualityGate()
        analyses: dict[str, dict[str, Any]] = {
            "efficiency": {
                "evaluation": "Zone 2 不足です",
            },
            "summary": {
                "overall": "理想的な配分です",
                "next_action": "もっと頑張りましょう",
                # no success_criterion
            },
        }
        result = gate.validate(analyses)
        assert result.passed is False
        # zone_contradiction + no_numeric_action + missing_success_criterion = 3
        assert len(result.warnings) >= 3
        check_names = {w.check_name for w in result.warnings}
        assert "zone_contradiction" in check_names
        assert "no_numeric_action" in check_names
        assert "missing_success_criterion" in check_names


# =============================================================================
# Integration Test
# =============================================================================


@pytest.mark.integration
class TestQualityGateIntegration:
    """Integration test for quality gate in report generation pipeline."""

    def test_e2e_quality_gate_in_report(self) -> None:
        """実レポート生成で品質ゲート動作確認."""
        # Mock all dependencies of ReportGeneratorWorker
        with patch(
            "garmin_mcp.reporting.report_generator_worker.GarminDBReader"
        ) as mock_reader_cls:
            mock_reader = MagicMock()
            mock_reader_cls.return_value = mock_reader

            # Setup mock returns
            mock_reader.get_activity_date.return_value = "2025-10-09"
            mock_reader.get_form_evaluations.return_value = None

            from garmin_mcp.reporting.report_generator_worker import (
                ReportGeneratorWorker,
            )

            worker = ReportGeneratorWorker(db_path="/tmp/test.duckdb")

            # Mock load methods
            worker.load_performance_data = MagicMock(  # type: ignore[method-assign]
                return_value={
                    "training_type": "aerobic_base",
                    "basic_metrics": {"distance_km": 7.0},
                    "run_metrics": {},
                }
            )

            section_analyses: dict[str, dict[str, Any]] = {
                "efficiency": {
                    "evaluation": "Zone 2 不足が見られます",
                },
                "summary": {
                    "overall": "理想的な配分で走れています",
                    "next_action": "もっと頑張りましょう",
                    # no success_criterion
                },
                "phase_evaluation": {},
                "split_analysis": {},
                "environment_analysis": {},
            }
            worker.load_section_analyses = MagicMock(  # type: ignore[method-assign]
                return_value=section_analyses
            )
            worker.load_splits_data = MagicMock(return_value=None)  # type: ignore[method-assign]
            worker._extract_phase_ratings = MagicMock(return_value={})  # type: ignore[method-assign]
            worker._generate_comparison_insights = MagicMock(  # type: ignore[method-assign]
                return_value=[]
            )
            worker._generate_hr_zone_pie_data = MagicMock(  # type: ignore[method-assign]
                return_value=None
            )

            # Mock renderer
            worker.renderer = MagicMock()
            worker.renderer.render_report.return_value = "# Report"
            worker.renderer.save_report.return_value = {"path": "/tmp/report.md"}

            result = worker.generate_report(12345678901, "2025-10-09")

            assert result["success"] is True
            assert "quality_warnings" in result
            assert len(result["quality_warnings"]) >= 3

            warning_checks = {w["check"] for w in result["quality_warnings"]}
            assert "zone_contradiction" in warning_checks
            assert "no_numeric_action" in warning_checks
            assert "missing_success_criterion" in warning_checks
