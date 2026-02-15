"""Unit tests for PhysiologicalCalculator class."""

from unittest.mock import MagicMock

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.physiological_calculator import (
    PhysiologicalCalculator,
)


@pytest.fixture
def mock_db_reader():
    """Create a mock GarminDBReader."""
    return MagicMock(spec=GarminDBReader)


@pytest.fixture
def calculator(mock_db_reader):
    """Create a PhysiologicalCalculator instance with mock db_reader."""
    return PhysiologicalCalculator(mock_db_reader)


class TestCalculatePhysiologicalIndicators:
    """Test calculate_physiological_indicators method."""

    @pytest.mark.unit
    def test_low_moderate_returns_empty_dict(self, calculator):
        """Should return empty dict for low_moderate training type."""
        result = calculator.calculate_physiological_indicators(
            training_type_category="low_moderate",
            vo2_max_data={"precise_value": 55.0},
            lactate_threshold_data={"speed_mps": 3.5},
            run_metrics={"avg_pace_seconds_per_km": 300},
        )

        assert result == {}

    @pytest.mark.unit
    def test_missing_run_metrics_returns_empty_dict(self, calculator):
        """Should return empty dict if run_metrics is None or empty."""
        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data={"precise_value": 55.0},
            lactate_threshold_data={"speed_mps": 3.5},
            run_metrics=None,
        )
        assert result == {}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data={"precise_value": 55.0},
            lactate_threshold_data={"speed_mps": 3.5},
            run_metrics={},
        )
        assert result == {}

    @pytest.mark.unit
    def test_vo2_max_utilization_very_high(self, calculator):
        """Should calculate VO2 max utilization >= 90% as '非常に高強度'."""
        vo2_max_data = {"precise_value": 55.0}
        run_metrics = {"avg_pace_seconds_per_km": 174}  # Fast pace for high utilization

        result = calculator.calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
        )

        # vVO2max = 55.0 / 3.5 = 15.71 km/h
        # vVO2max pace = 3600 / 15.71 = 229.15 sec/km
        # Utilization = (229.15 / 174) * 100 = 131.7%
        assert "vo2_max_utilization" in result
        assert result["vo2_max_utilization"] >= 90
        assert result["vo2_max_utilization_eval"] == "非常に高強度"
        assert (
            "VO2 max（最大酸素摂取量）の大幅向上" in result["vo2_max_expected_effect"]
        )

    @pytest.mark.unit
    def test_vo2_max_utilization_high(self, calculator):
        """Should calculate VO2 max utilization 80-90% as '高強度'."""
        vo2_max_data = {"precise_value": 55.0}
        run_metrics = {"avg_pace_seconds_per_km": 258}  # Moderate pace

        result = calculator.calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
        )

        # vVO2max pace = 229.15 sec/km
        # Utilization = (229.15 / 258) * 100 = 88.8%
        assert "vo2_max_utilization" in result
        assert 80 <= result["vo2_max_utilization"] < 90
        assert result["vo2_max_utilization_eval"] == "高強度（閾値〜VO2max）"
        assert "乳酸閾値とVO2 maxの両方が向上" in result["vo2_max_expected_effect"]

    @pytest.mark.unit
    def test_vo2_max_utilization_moderate_high(self, calculator):
        """Should calculate VO2 max utilization 70-80% as '中高強度'."""
        vo2_max_data = {"precise_value": 55.0}
        run_metrics = {"avg_pace_seconds_per_km": 300}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
        )

        # Utilization = (229.15 / 300) * 100 = 76.4%
        assert "vo2_max_utilization" in result
        assert 70 <= result["vo2_max_utilization"] < 80
        assert result["vo2_max_utilization_eval"] == "中高強度（テンポ〜閾値）"
        assert "主に乳酸閾値の向上" in result["vo2_max_expected_effect"]

    @pytest.mark.unit
    def test_vo2_max_utilization_moderate(self, calculator):
        """Should calculate VO2 max utilization < 70% as '中強度'."""
        vo2_max_data = {"precise_value": 55.0}
        run_metrics = {"avg_pace_seconds_per_km": 360}  # Slow pace

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
        )

        # Utilization = (229.15 / 360) * 100 = 63.7%
        assert "vo2_max_utilization" in result
        assert result["vo2_max_utilization"] < 70
        assert result["vo2_max_utilization_eval"] == "中強度"
        assert "有酸素基礎の強化" in result["vo2_max_expected_effect"]

    @pytest.mark.unit
    def test_threshold_pace_equal(self, calculator):
        """Should identify threshold pace as equal within 5 sec/km."""
        lactate_threshold_data = {"speed_mps": 3.5}  # 1000/3.5 = 285.7 sec/km
        run_metrics = {"avg_pace_seconds_per_km": 287}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # pace_diff = 287 - 285.7 = 1.3 sec/km (within 5)
        assert "threshold_pace_comparison" in result
        assert result["threshold_pace_comparison"] == "閾値ペースと同等"

    @pytest.mark.unit
    def test_threshold_pace_slower(self, calculator):
        """Should identify pace slower than threshold."""
        lactate_threshold_data = {"speed_mps": 3.5}  # 285.7 sec/km
        run_metrics = {"avg_pace_seconds_per_km": 300}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # pace_diff = 300 - 285.7 = 14.3 sec/km (slower)
        assert "threshold_pace_comparison" in result
        assert "閾値より14秒/km遅い" in result["threshold_pace_comparison"]

    @pytest.mark.unit
    def test_threshold_pace_faster(self, calculator):
        """Should identify pace faster than threshold."""
        lactate_threshold_data = {"speed_mps": 3.5}  # 285.7 sec/km
        run_metrics = {"avg_pace_seconds_per_km": 270}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # pace_diff = 270 - 285.7 = -15.7 sec/km (faster)
        assert "threshold_pace_comparison" in result
        assert "閾値より16秒/km速い" in result["threshold_pace_comparison"]

    @pytest.mark.unit
    def test_ftp_percentage_zone_1(self, calculator):
        """Should calculate FTP percentage and identify Zone 1."""
        lactate_threshold_data = {"functional_threshold_power": 300}
        run_metrics = {"avg_power": 150}  # 50% FTP

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result["ftp_percentage"] == 50.0
        assert result["work_avg_power"] == 150
        assert result["power_zone_name"] == "Zone 1 (リカバリー)"

    @pytest.mark.unit
    def test_ftp_percentage_zone_4(self, calculator):
        """Should identify Zone 4 (threshold)."""
        lactate_threshold_data = {"functional_threshold_power": 300}
        run_metrics = {"avg_power": 285}  # 95% FTP

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result["ftp_percentage"] == 95.0
        assert result["power_zone_name"] == "Zone 4 (閾値)"

    @pytest.mark.unit
    def test_ftp_percentage_zone_7(self, calculator):
        """Should identify Zone 7 (neuromuscular)."""
        lactate_threshold_data = {"functional_threshold_power": 300}
        run_metrics = {"avg_power": 480}  # 160% FTP

        result = calculator.calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        assert result["ftp_percentage"] == 160.0
        assert result["power_zone_name"] == "Zone 7 (神経筋)"

    @pytest.mark.unit
    def test_threshold_hr_effect_above(self, calculator):
        """Should identify training above threshold HR."""
        lactate_threshold_data = {"heart_rate": 165, "speed_mps": 3.5}
        run_metrics = {"avg_hr": 175, "avg_pace_seconds_per_km": 270}

        result = calculator.calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # hr_diff = 175 - 165 = 10 (> 5)
        assert "threshold_expected_effect" in result
        assert "VO2 maxの向上効果" in result["threshold_expected_effect"]

    @pytest.mark.unit
    def test_threshold_hr_effect_at_threshold(self, calculator):
        """Should identify training at threshold HR."""
        lactate_threshold_data = {"heart_rate": 165, "speed_mps": 3.5}
        run_metrics = {"avg_hr": 166, "avg_pace_seconds_per_km": 285}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # hr_diff = 166 - 165 = 1 (within -5 to 5)
        assert "threshold_expected_effect" in result
        assert "乳酸閾値の向上に最適" in result["threshold_expected_effect"]

    @pytest.mark.unit
    def test_threshold_hr_effect_below(self, calculator):
        """Should identify training below threshold HR."""
        lactate_threshold_data = {"heart_rate": 165, "speed_mps": 3.5}
        run_metrics = {"avg_hr": 155, "avg_pace_seconds_per_km": 300}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
        )

        # hr_diff = 155 - 165 = -10 (< -5)
        assert "threshold_expected_effect" in result
        assert "閾値ペース感覚の習得" in result["threshold_expected_effect"]

    @pytest.mark.unit
    def test_zone_4_ratio_tempo_threshold(self, calculator):
        """Should calculate Zone 4 ratio for tempo_threshold training."""
        hr_zone_times = [
            (1, 60),  # Zone 1: 60 sec
            (2, 180),  # Zone 2: 180 sec
            (3, 300),  # Zone 3: 300 sec
            (4, 900),  # Zone 4: 900 sec
            (5, 60),  # Zone 5: 60 sec
        ]
        run_metrics = {"avg_pace_seconds_per_km": 285}

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=None,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
            hr_zone_times=hr_zone_times,
        )

        # Total time = 1500 sec
        # Zone 4 time = 900 sec
        # Ratio = (900 / 1500) * 100 = 60.0%
        assert result["zone_4_ratio"] == 60.0

    @pytest.mark.unit
    def test_zone_4_ratio_not_calculated_for_interval(self, calculator):
        """Should not calculate Zone 4 ratio for interval_sprint training."""
        hr_zone_times = [(4, 900), (5, 600)]
        run_metrics = {"avg_pace_seconds_per_km": 240}

        result = calculator.calculate_physiological_indicators(
            training_type_category="interval_sprint",
            vo2_max_data=None,
            lactate_threshold_data=None,
            run_metrics=run_metrics,
            hr_zone_times=hr_zone_times,
        )

        assert "zone_4_ratio" not in result

    @pytest.mark.unit
    def test_comprehensive_tempo_threshold_with_all_data(self, calculator):
        """Should calculate all indicators for tempo_threshold with complete data."""
        vo2_max_data = {"precise_value": 55.0}
        lactate_threshold_data = {
            "speed_mps": 3.5,
            "heart_rate": 165,
            "functional_threshold_power": 300,
        }
        run_metrics = {
            "avg_pace_seconds_per_km": 285,
            "avg_hr": 166,
            "avg_power": 285,
        }
        hr_zone_times = [(3, 600), (4, 900)]

        result = calculator.calculate_physiological_indicators(
            training_type_category="tempo_threshold",
            vo2_max_data=vo2_max_data,
            lactate_threshold_data=lactate_threshold_data,
            run_metrics=run_metrics,
            hr_zone_times=hr_zone_times,
        )

        # Should have all indicators
        assert "vo2_max_utilization" in result
        assert "vo2_max_utilization_eval" in result
        assert "vo2_max_expected_effect" in result
        assert "threshold_pace_formatted" in result
        assert "threshold_pace_comparison" in result
        assert "ftp_percentage" in result
        assert "work_avg_power" in result
        assert "power_zone_name" in result
        assert "threshold_expected_effect" in result
        assert "zone_4_ratio" in result


class TestCalculatePaceCorrectedFormEfficiency:
    """Test calculate_pace_corrected_form_efficiency method."""

    @pytest.mark.unit
    def test_gct_efficiency_excellent(self, calculator):
        """Should calculate GCT score < -5% as '優秀'."""
        avg_pace = 300  # sec/km
        form_eff = {
            "gct_average": 230,  # Low GCT (good)
            "vo_average": 7.0,
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        # baseline_gct = 230 + (300 - 240) * 0.22 = 230 + 13.2 = 243.2
        # gct_score = ((230 - 243.2) / 243.2) * 100 = -5.4%
        assert result["gct"]["baseline"] == 243.2
        assert result["gct"]["score"] == -5.4
        assert result["gct"]["label"] == "優秀"
        assert result["gct"]["rating_score"] == 5.0

    @pytest.mark.unit
    def test_gct_efficiency_good(self, calculator):
        """Should calculate GCT score within ±5% as '良好'."""
        avg_pace = 300
        form_eff = {
            "gct_average": 243,  # Near baseline
            "vo_average": 7.0,
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        # baseline_gct = 243.2
        # gct_score = ((243 - 243.2) / 243.2) * 100 = -0.08%
        assert abs(result["gct"]["score"]) <= 5
        assert result["gct"]["label"] == "良好"
        assert result["gct"]["rating_score"] == 4.0

    @pytest.mark.unit
    def test_gct_efficiency_needs_improvement(self, calculator):
        """Should calculate GCT score > 5% as '要改善'."""
        avg_pace = 300
        form_eff = {
            "gct_average": 260,  # High GCT (bad)
            "vo_average": 7.0,
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        # gct_score = ((260 - 243.2) / 243.2) * 100 = 6.9%
        assert result["gct"]["score"] > 5
        assert result["gct"]["label"] == "要改善"
        assert result["gct"]["rating_score"] == 3.0

    @pytest.mark.unit
    def test_vo_efficiency_excellent(self, calculator):
        """Should calculate VO score < -5% as '優秀'."""
        avg_pace = 300
        form_eff = {
            "gct_average": 243,
            "vo_average": 6.5,  # Low VO (good)
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        # baseline_vo = 6.8 + (300 - 240) * 0.004 = 6.8 + 0.24 = 7.04
        # vo_score = ((6.5 - 7.04) / 7.04) * 100 = -7.7%
        assert result["vo"]["baseline"] == 7.04
        assert result["vo"]["score"] == -7.7
        assert result["vo"]["label"] == "優秀"
        assert result["vo"]["rating_score"] == 5.0

    @pytest.mark.unit
    def test_vo_efficiency_good(self, calculator):
        """Should calculate VO score within ±5% as '良好'."""
        avg_pace = 300
        form_eff = {
            "gct_average": 243,
            "vo_average": 7.04,  # At baseline
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        # vo_score = ((7.04 - 7.04) / 7.04) * 100 = 0.0%
        assert abs(result["vo"]["score"]) <= 5
        assert result["vo"]["label"] == "良好"
        assert result["vo"]["rating_score"] == 4.0

    @pytest.mark.unit
    def test_vr_ideal_range(self, calculator):
        """Should identify VR in ideal range (8.0-9.5%)."""
        avg_pace = 300
        form_eff = {
            "gct_average": 243,
            "vo_average": 7.0,
            "vr_average": 8.5,  # In ideal range
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        assert result["vr"]["actual"] == 8.5
        assert result["vr"]["label"] == "理想範囲内"
        assert result["vr"]["rating_score"] == 5.0

    @pytest.mark.unit
    def test_vr_needs_improvement(self, calculator):
        """Should identify VR outside ideal range."""
        avg_pace = 300
        form_eff = {
            "gct_average": 243,
            "vo_average": 7.0,
            "vr_average": 12.0,  # Too high
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        assert result["vr"]["actual"] == 12.0
        assert result["vr"]["label"] == "要改善"
        assert result["vr"]["rating_score"] == 3.5

    @pytest.mark.unit
    def test_power_efficiency_stable(self, calculator):
        """Should identify power as stable (within ±3%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_power=285.0,
            baseline_power=280.0,
        )

        # power_score = ((285 - 280) / 280) * 100 = 1.8%
        assert "power" in result
        assert result["power"]["score"] == 1.8
        assert result["power"]["label"] == "安定"
        assert result["power"]["rating_score"] == 4.5

    @pytest.mark.unit
    def test_power_efficiency_increased(self, calculator):
        """Should identify power as increased (> 3%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_power=300.0,
            baseline_power=280.0,
        )

        # power_score = ((300 - 280) / 280) * 100 = 7.1%
        assert result["power"]["score"] == 7.1
        assert result["power"]["label"] == "上昇"
        assert result["power"]["rating_score"] == 4.0

    @pytest.mark.unit
    def test_power_efficiency_improved(self, calculator):
        """Should identify power as improved (< -3%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_power=270.0,
            baseline_power=280.0,
        )

        # power_score = ((270 - 280) / 280) * 100 = -3.6%
        assert result["power"]["score"] == -3.6
        assert result["power"]["label"] == "効率向上"
        assert result["power"]["rating_score"] == 5.0

    @pytest.mark.unit
    def test_stride_efficiency_extended(self, calculator):
        """Should identify stride as extended (0-5%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_stride=104.0,  # cm
            baseline_stride=100.0,  # cm
        )

        # stride_score = ((104 - 100) / 100) * 100 = 4.0%
        assert "stride" in result
        assert result["stride"]["actual"] == 1.04  # Converted to m
        assert result["stride"]["baseline"] == 1.0  # Converted to m
        assert result["stride"]["score"] == 4.0
        assert result["stride"]["label"] == "拡大"
        assert result["stride"]["rating_score"] == 4.5

    @pytest.mark.unit
    def test_stride_efficiency_stable(self, calculator):
        """Should identify stride as stable (negative score within 2%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_stride=99.0,  # -1.0% score
            baseline_stride=100.0,
        )

        # stride_score = -1.0% (falls into abs(score) <= 2 but not 0 <= score <= 5)
        assert abs(result["stride"]["score"]) <= 2
        assert result["stride"]["label"] == "安定"
        assert result["stride"]["rating_score"] == 4.5

    @pytest.mark.unit
    def test_stride_efficiency_shortened(self, calculator):
        """Should identify stride as shortened (< -2%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_stride=95.0,
            baseline_stride=100.0,
        )

        # stride_score = -5.0%
        assert result["stride"]["score"] == -5.0
        assert result["stride"]["label"] == "短縮"
        assert result["stride"]["rating_score"] == 4.0

    @pytest.mark.unit
    def test_stride_efficiency_greatly_extended(self, calculator):
        """Should identify stride as greatly extended (> 5%)."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_stride=110.0,
            baseline_stride=100.0,
        )

        # stride_score = 10.0%
        assert result["stride"]["score"] == 10.0
        assert result["stride"]["label"] == "大幅拡大"
        assert result["stride"]["rating_score"] == 4.0

    @pytest.mark.unit
    def test_no_power_or_stride_data(self, calculator):
        """Should handle missing power and stride data."""
        avg_pace = 300
        form_eff = {"gct_average": 243, "vo_average": 7.0, "vr_average": 8.5}

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
        )

        assert "power" not in result
        assert "stride" not in result
        assert "gct" in result
        assert "vo" in result
        assert "vr" in result

    @pytest.mark.unit
    def test_complete_data_with_all_metrics(self, calculator):
        """Should calculate all metrics when complete data provided."""
        avg_pace = 300
        form_eff = {
            "gct_average": 230,
            "vo_average": 6.5,
            "vr_average": 8.5,
        }

        result = calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km=avg_pace,
            form_eff=form_eff,
            run_power=285.0,
            run_stride=104.0,
            baseline_power=280.0,
            baseline_stride=100.0,
        )

        assert "gct" in result
        assert "vo" in result
        assert "vr" in result
        assert "power" in result
        assert "stride" in result
        assert result["avg_pace_seconds"] == 300


class TestBuildFormEfficiencyTable:
    """Test build_form_efficiency_table method."""

    @pytest.mark.unit
    def test_build_table_basic_metrics(self, calculator):
        """Should build table with GCT, VO, VR metrics."""
        pace_corrected_data = {
            "avg_pace_seconds": 300,
            "gct": {
                "actual": 230.0,
                "baseline": 243.2,
                "score": -5.4,
                "label": "優秀",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
            "vo": {
                "actual": 6.50,
                "baseline": 7.04,
                "score": -7.7,
                "label": "優秀",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
            "vr": {
                "actual": 8.50,
                "label": "理想範囲内",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
        }

        result = calculator.build_form_efficiency_table(pace_corrected_data)

        assert "overall_form_score" in result
        assert "form_efficiency_table" in result
        assert len(result["form_efficiency_table"]) == 3

        # Check GCT row
        gct_row = result["form_efficiency_table"][0]
        assert gct_row["metric_name"] == "接地時間"
        assert gct_row["actual_value"] == "230.0ms"
        assert gct_row["baseline_value"] == "243.2ms"
        assert "**-5.4%** 優秀" in gct_row["adjusted_score"]
        assert "★★★★★ 5.0" in gct_row["rating"]

        # Check VO row
        vo_row = result["form_efficiency_table"][1]
        assert vo_row["metric_name"] == "垂直振幅"
        assert vo_row["actual_value"] == "6.50cm"
        assert vo_row["baseline_value"] == "7.04cm"

        # Check VR row
        vr_row = result["form_efficiency_table"][2]
        assert vr_row["metric_name"] == "垂直比率"
        assert vr_row["actual_value"] == "8.50%"
        assert vr_row["baseline_value"] == "8.0-9.5%"
        assert vr_row["adjusted_score"] == "理想範囲内"

    @pytest.mark.unit
    def test_build_table_with_power_and_stride(self, calculator):
        """Should build table with power and stride metrics."""
        pace_corrected_data = {
            "avg_pace_seconds": 300,
            "gct": {
                "actual": 243.0,
                "baseline": 243.2,
                "score": -0.1,
                "label": "良好",
                "rating_stars": "★★★★☆",
                "rating_score": 4.0,
            },
            "vo": {
                "actual": 7.00,
                "baseline": 7.04,
                "score": -0.6,
                "label": "良好",
                "rating_stars": "★★★★☆",
                "rating_score": 4.0,
            },
            "vr": {
                "actual": 8.50,
                "label": "理想範囲内",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
            "power": {
                "actual": 285.0,
                "baseline": 280.0,
                "score": 1.8,
                "label": "安定",
                "rating_stars": "★★★★☆",
                "rating_score": 4.5,
            },
            "stride": {
                "actual": 1.04,
                "baseline": 1.00,
                "score": 4.0,
                "label": "拡大",
                "rating_stars": "★★★★☆",
                "rating_score": 4.5,
            },
        }

        result = calculator.build_form_efficiency_table(pace_corrected_data)

        assert len(result["form_efficiency_table"]) == 5

        # Check power row
        power_row = result["form_efficiency_table"][3]
        assert power_row["metric_name"] == "パワー"
        assert power_row["actual_value"] == "285W"
        assert power_row["baseline_value"] == "280W（類似平均）"
        assert "**+1.8%** 安定" in power_row["adjusted_score"]

        # Check stride row
        stride_row = result["form_efficiency_table"][4]
        assert stride_row["metric_name"] == "ストライド長"
        assert stride_row["actual_value"] == "1.04m"
        assert stride_row["baseline_value"] == "1.00m（類似平均）"
        assert "**+4.0%** 拡大" in stride_row["adjusted_score"]

    @pytest.mark.unit
    def test_overall_form_score_calculation(self, calculator):
        """Should calculate overall form score as average of all ratings."""
        pace_corrected_data = {
            "avg_pace_seconds": 300,
            "gct": {
                "actual": 243.0,
                "baseline": 243.2,
                "score": -0.1,
                "label": "良好",
                "rating_stars": "★★★★☆",
                "rating_score": 4.0,
            },
            "vo": {
                "actual": 7.00,
                "baseline": 7.04,
                "score": -0.6,
                "label": "良好",
                "rating_stars": "★★★★★",
                "rating_score": 5.0,
            },
            "vr": {
                "actual": 8.50,
                "label": "理想範囲内",
                "rating_stars": "★★★★☆",
                "rating_score": 4.5,
            },
        }

        result = calculator.build_form_efficiency_table(pace_corrected_data)

        # Average = (4.0 + 5.0 + 4.5) / 3 = 4.5
        assert "4.5/5.0" in result["overall_form_score"]
        assert "★★★★☆" in result["overall_form_score"]


class TestCalculateRunPhasePowerStride:
    """Test calculate_run_phase_power_stride method."""

    @pytest.mark.unit
    def test_returns_power_and_stride(self, calculator, mock_db_reader):
        """Should return power and stride from db query."""
        mock_db_reader.execute_read_query.return_value = [(285.5, 103.75)]

        result = calculator.calculate_run_phase_power_stride(activity_id=12345)

        assert result["avg_power"] == 285.5
        assert result["avg_stride"] == 103.75
        mock_db_reader.execute_read_query.assert_called_once()

    @pytest.mark.unit
    def test_returns_none_when_no_data(self, calculator, mock_db_reader):
        """Should return None values when no data available."""
        mock_db_reader.execute_read_query.return_value = []

        result = calculator.calculate_run_phase_power_stride(activity_id=12345)

        assert result["avg_power"] is None
        assert result["avg_stride"] is None

    @pytest.mark.unit
    def test_returns_none_when_result_is_null(self, calculator, mock_db_reader):
        """Should return None values when query returns NULL."""
        mock_db_reader.execute_read_query.return_value = [(None, None)]

        result = calculator.calculate_run_phase_power_stride(activity_id=12345)

        assert result["avg_power"] is None
        assert result["avg_stride"] is None

    @pytest.mark.unit
    def test_handles_exception(self, calculator, mock_db_reader):
        """Should handle exceptions and return None values."""
        mock_db_reader.execute_read_query.side_effect = Exception("Database error")

        result = calculator.calculate_run_phase_power_stride(activity_id=12345)

        assert result["avg_power"] is None
        assert result["avg_stride"] is None


class TestCalculatePowerStrideBaselines:
    """Test calculate_power_stride_baselines method."""

    @pytest.mark.unit
    def test_uses_similar_workouts_when_provided(self, calculator, mock_db_reader):
        """Should use similar_workouts IDs when provided."""
        similar_workouts = {
            "similar_activities": [
                {"activity_id": 100},
                {"activity_id": 101},
                {"activity_id": 102},
            ]
        }
        mock_db_reader.execute_read_query.return_value = [(280.0, 100.0)]

        result = calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=similar_workouts,
            training_type="tempo",
        )

        # Should query 3 similar activities
        assert mock_db_reader.execute_read_query.call_count == 3
        assert result["baseline_power"] == 280.0
        assert result["baseline_stride"] == 100.0

    @pytest.mark.unit
    def test_falls_back_to_distance_pace_query(self, calculator, mock_db_reader):
        """Should fall back to distance/pace-based query when no similar_workouts."""
        # First call: get current activity data
        # Second call: get similar activities
        # Third+ calls: get power/stride for each similar activity
        mock_db_reader.execute_read_query.side_effect = [
            [(10.0, 300.0)],  # Current activity
            [(100,), (101,)],  # Similar activity IDs
            [(280.0, 100.0)],  # Power/stride for ID 100
            [(285.0, 102.0)],  # Power/stride for ID 101
        ]

        result = calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=None,
            training_type="base",
        )

        assert mock_db_reader.execute_read_query.call_count == 4
        # Average: (280 + 285) / 2 = 282.5, (100 + 102) / 2 = 101.0
        assert result["baseline_power"] == 282.5
        assert result["baseline_stride"] == 101.0

    @pytest.mark.unit
    def test_returns_none_when_no_current_activity(self, calculator, mock_db_reader):
        """Should return None when current activity not found."""
        mock_db_reader.execute_read_query.return_value = []

        result = calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=None,
        )

        assert result["baseline_power"] is None
        assert result["baseline_stride"] is None

    @pytest.mark.unit
    def test_returns_none_when_no_similar_activities(self, calculator, mock_db_reader):
        """Should return None when no similar activities found."""
        mock_db_reader.execute_read_query.side_effect = [
            [(10.0, 300.0)],  # Current activity
            [],  # No similar activities
        ]

        result = calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=None,
        )

        assert result["baseline_power"] is None
        assert result["baseline_stride"] is None

    @pytest.mark.unit
    def test_uses_run_phase_for_structured_training(self, calculator, mock_db_reader):
        """Should filter by role_phase='run' for structured training types."""
        similar_workouts = {"similar_activities": [{"activity_id": 100}]}
        mock_db_reader.execute_read_query.return_value = [(280.0, 100.0)]

        calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=similar_workouts,
            training_type="tempo",  # Structured type
        )

        # Check that query includes role_phase = 'run'
        call_args = mock_db_reader.execute_read_query.call_args[0][0]
        assert "role_phase = 'run'" in call_args

    @pytest.mark.unit
    def test_uses_all_splits_for_base_training(self, calculator, mock_db_reader):
        """Should use all splits for base/recovery training types."""
        similar_workouts = {"similar_activities": [{"activity_id": 100}]}
        mock_db_reader.execute_read_query.return_value = [(280.0, 100.0)]

        calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=similar_workouts,
            training_type="base",  # Non-structured type
        )

        # Check that query does NOT include role_phase filter
        call_args = mock_db_reader.execute_read_query.call_args[0][0]
        assert "role_phase = 'run'" not in call_args

    @pytest.mark.unit
    def test_handles_exception(self, calculator, mock_db_reader):
        """Should handle exceptions and return None values."""
        mock_db_reader.execute_read_query.side_effect = Exception("Database error")

        result = calculator.calculate_power_stride_baselines(
            activity_id=12345,
            similar_workouts=None,
        )

        assert result["baseline_power"] is None
        assert result["baseline_stride"] is None
