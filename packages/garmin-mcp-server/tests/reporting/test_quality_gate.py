"""Tests for QualityGate advisory validation before report output."""

from __future__ import annotations

import pytest

from garmin_mcp.reporting.quality_gate import QualityGate


@pytest.mark.unit
class TestCheckZoneContradiction:
    """QualityGate.check_zone_contradiction() tests."""

    def test_detect_zone_contradiction(self) -> None:
        """Zone不足評価 + '理想的配分' テキスト共存 -> warning検出."""
        gate = QualityGate()
        section_analyses = {
            "efficiency": {
                "evaluation": "Zone 2 の比率が不足しています。",
            },
            "summary": {
                "summary": "理想的配分でトレーニングができました。",
            },
        }
        warnings = gate.check_zone_contradiction(section_analyses)
        assert len(warnings) >= 1
        assert any(
            "矛盾" in w.message or "contradiction" in w.message.lower()
            for w in warnings
        )

    def test_no_zone_contradiction(self) -> None:
        """Zone十分評価 + '理想的配分' -> warning なし."""
        gate = QualityGate()
        section_analyses = {
            "efficiency": {
                "evaluation": "Zone 2 の比率が十分です。",
            },
            "summary": {
                "summary": "理想的配分でトレーニングができました。",
            },
        }
        warnings = gate.check_zone_contradiction(section_analyses)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckSingleAction:
    """QualityGate.check_single_action() tests."""

    def test_detect_multiple_actions(self) -> None:
        """next_action に2つ以上のアクション -> warning検出."""
        gate = QualityGate()
        summary = {
            "recommendations": "1. HR 135-140 bpm で走る\n2. ケイデンス 180 spm を目指す",
        }
        warnings = gate.check_single_action(summary)
        assert len(warnings) >= 1
        assert any("単一" in w.message or "複数" in w.message for w in warnings)

    def test_single_action_passes(self) -> None:
        """next_action が1つ -> warning なし."""
        gate = QualityGate()
        summary = {
            "recommendations": "HR 135-140 bpm を維持して走る",
        }
        warnings = gate.check_single_action(summary)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckNumericAction:
    """QualityGate.check_numeric_action() tests."""

    def test_detect_no_numeric_action(self) -> None:
        """next_action='もっと練習しましょう'（数値なし） -> warning検出."""
        gate = QualityGate()
        summary = {
            "recommendations": "もっと練習しましょう",
        }
        warnings = gate.check_numeric_action(summary)
        assert len(warnings) >= 1
        assert any(
            "数値" in w.message or "numeric" in w.message.lower() for w in warnings
        )

    def test_numeric_action_passes(self) -> None:
        """next_action='HR 135-140 bpm を維持' -> warning なし."""
        gate = QualityGate()
        summary = {
            "recommendations": "HR 135-140 bpm を維持",
        }
        warnings = gate.check_numeric_action(summary)
        assert len(warnings) == 0


@pytest.mark.unit
class TestCheckSuccessCriterion:
    """QualityGate.check_success_criterion() tests."""

    def test_detect_missing_success_criterion(self) -> None:
        """success_criterion 未設定 -> warning検出."""
        gate = QualityGate()
        summary: dict[str, object] = {
            "next_run_target": {
                "recommended_type": "easy",
            },
        }
        warnings = gate.check_success_criterion(summary)
        assert len(warnings) >= 1
        assert any(
            "成功判定" in w.message or "success" in w.message.lower() for w in warnings
        )

    def test_success_criterion_passes(self) -> None:
        """success_criterion='Zone 2 > 60%' -> warning なし."""
        gate = QualityGate()
        summary: dict[str, object] = {
            "next_run_target": {
                "recommended_type": "easy",
                "success_criterion": "Zone 2 > 60%",
            },
        }
        warnings = gate.check_success_criterion(summary)
        assert len(warnings) == 0


@pytest.mark.unit
class TestValidate:
    """QualityGate.validate() integration tests."""

    def test_all_checks_pass(self) -> None:
        """全チェック通過 -> warnings=[], passed=True."""
        gate = QualityGate()
        section_analyses = {
            "efficiency": {
                "evaluation": "Zone 2 の比率が十分です。良い配分です。",
            },
            "summary": {
                "summary": "良いトレーニングでした。",
                "recommendations": "次回は HR 135-140 bpm で走る",
                "next_run_target": {
                    "recommended_type": "easy",
                    "success_criterion": "Zone 2 比率 60% 以上で成功",
                },
            },
        }
        result = gate.validate(section_analyses)
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_multiple_warnings(self) -> None:
        """複数チェック不合格 -> 全warning集約."""
        gate = QualityGate()
        section_analyses = {
            "efficiency": {
                "evaluation": "Zone 2 の比率が不足しています。",
            },
            "summary": {
                "summary": "理想的配分でトレーニングができました。",
                "recommendations": "もっと頑張りましょう",
                "next_run_target": {
                    "recommended_type": "easy",
                },
            },
        }
        result = gate.validate(section_analyses)
        assert result.passed is False
        assert len(result.warnings) >= 3


@pytest.mark.integration
class TestQualityGateIntegration:
    """Integration test for quality gate in report pipeline."""

    def test_e2e_quality_gate_in_report(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """実レポート生成で品質ゲート動作確認."""
        gate = QualityGate()
        # Simulate a realistic section_analyses from the pipeline
        section_analyses = {
            "efficiency": {
                "evaluation": "HR Zone 配分は概ね適切で、Zone 2 中心のトレーニングが実施されています。",
                "hr_zone_assessment": {"zone2_ratio": 0.65},
            },
            "summary": {
                "summary": "ペースの安定したイージーランでした。",
                "key_strengths": ["安定したペース維持"],
                "improvement_areas": ["ケイデンス向上の余地あり"],
                "recommendations": "次回は HR 135-140 bpm を維持し、ケイデンス 175 spm を目指す",
                "next_run_target": {
                    "recommended_type": "easy",
                    "target_hr_low": 135,
                    "target_hr_high": 140,
                    "success_criterion": "Zone 2 比率 60% 以上で成功",
                },
            },
            "phase_evaluation": {"overall_rating": "****"},
            "split_analysis": {"highlights": "安定したスプリット"},
            "environment_analysis": {"weather_impact": "影響なし"},
        }
        result = gate.validate(section_analyses)
        assert result.passed is True
        assert len(result.warnings) == 0
