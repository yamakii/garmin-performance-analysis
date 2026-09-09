"""Canonical training category mapping and the moderate (controlled zone 3) category."""

import pytest

from garmin_mcp.database.inserters.hr_efficiency import (
    _canonical_training_category,
    _extract_hr_efficiency_from_raw,
    _resolve_intensity_category,
)
from tests.database.inserters.hr_efficiency._helpers import _write_raw_files


class TestCanonicalTrainingCategory:
    """Test suite for _canonical_training_category and category-based ratings."""

    @pytest.mark.unit
    def test_canonical_category_maps_real_labels(self):
        """raw/fallback labels map to the correct canonical intensity category."""
        assert _canonical_training_category("aerobic_base") == "easy"
        assert _canonical_training_category("recovery") == "easy"
        assert _canonical_training_category("low_moderate") == "easy"
        assert _canonical_training_category("warmup") == "easy"
        assert _canonical_training_category("tempo") == "tempo"
        assert _canonical_training_category("tempo_run") == "tempo"
        assert _canonical_training_category("lactate_threshold") == "threshold"
        assert _canonical_training_category("threshold_work") == "threshold"
        assert _canonical_training_category("vo2max") == "vo2max"
        assert _canonical_training_category("anaerobic_capacity") == "vo2max"
        assert _canonical_training_category("speed") == "vo2max"
        assert _canonical_training_category("interval_sprint") == "vo2max"
        assert _canonical_training_category("unknown") == "unknown"
        assert _canonical_training_category("mixed_effort") == "unknown"
        assert _canonical_training_category(None) == "unknown"

    @pytest.mark.unit
    def test_easy_zone1_dominant_not_poor(self, tmp_path):
        """Regression (activity 23508330663): easy run dominated by Zone1 must not
        be rated Poor. zone1=57.6, zone2=42.4 → Excellent."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 57.6, 2: 42.4}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"
        assert result["training_quality"] in {"Excellent", "Good"}

    @pytest.mark.unit
    def test_recovery_all_zone1_excellent(self, tmp_path):
        """recovery with all time in Zone1 → Excellent (judged on Zone1-2)."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 100.0}, "RECOVERY"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_tempo_scored_by_zone34(self, tmp_path):
        """tempo scored on Zone3-4: zone3+zone4=65 → Excellent (not old else path)."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 35.0, 3: 35.0, 4: 30.0}, "TEMPO"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_lactate_threshold_scored_by_zone34(self, tmp_path):
        """lactate_threshold scored on Zone3-4: zone3+zone4=45 → Good."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 55.0, 3: 25.0, 4: 20.0}, "LACTATE_THRESHOLD"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Good"

    @pytest.mark.unit
    def test_vo2max_scored_by_zone45(self, tmp_path):
        """vo2max scored on Zone4-5: zone4+zone5=55 → Excellent."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 45.0, 4: 30.0, 5: 25.0}, "VO2MAX"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_easy_drift_to_zone3_downgraded(self, tmp_path):
        """easy run that drifts into Zone3: zone1+zone2=55, zone3=45 → Fair/Poor."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 30.0, 2: 25.0, 3: 45.0}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] in {"Fair", "Poor"}

    @pytest.mark.unit
    def test_unknown_not_harshly_penalized(self, tmp_path):
        """unknown type never rated Poor: zone1+zone2+zone3=75 → Good."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 25.0, 2: 25.0, 3: 25.0, 4: 25.0}, "UNKNOWN"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] != "Poor"

    @pytest.mark.unit
    def test_resolve_moderate_from_controlled_zone3(self):
        """Zone3-dominant aerobic_base with negligible Zone4-5 → 'moderate'."""
        assert (
            _resolve_intensity_category(
                "aerobic_base",
                zone1_pct=5.0,
                zone2_pct=19.0,
                zone3_pct=76.0,
                zone4_pct=0.0,
                zone5_pct=0.0,
                primary_zone="Zone 3",
            )
            == "moderate"
        )

    @pytest.mark.unit
    def test_moderate_category_from_controlled_zone3(self, tmp_path):
        """Regression (activity 23534377199): controlled Zone3 moderate run must not
        be rated Poor. zone1=5, zone2=19, zone3=76 → Excellent (aerobic Zone2-3 band).
        """
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 5.0, 2: 19.0, 3: 76.0}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"
        assert result["training_quality"] in {"Excellent", "Good"}

    @pytest.mark.unit
    def test_easy_drift_to_zone3_stays_easy(self):
        """A mild drift into Zone3 (zone3=45 < 50, not dominant) stays 'easy' and is
        NOT promoted to 'moderate' — preserves test_easy_drift_to_zone3_downgraded."""
        assert (
            _resolve_intensity_category(
                "aerobic_base",
                zone1_pct=30.0,
                zone2_pct=25.0,
                zone3_pct=45.0,
                zone4_pct=0.0,
                zone5_pct=0.0,
                primary_zone="Zone 3",
            )
            == "easy"
        )

    @pytest.mark.unit
    def test_moderate_requires_negligible_z45(self, tmp_path):
        """Zone3-dominant but with real Zone4-5 work (>=15%) is NOT 'moderate' — it
        keeps its label path so genuine threshold/VO2 sessions are not masked."""
        assert (
            _resolve_intensity_category(
                "aerobic_base",
                zone1_pct=15.0,
                zone2_pct=0.0,
                zone3_pct=60.0,
                zone4_pct=25.0,
                zone5_pct=0.0,
                primary_zone="Zone 3",
            )
            != "moderate"
        )

    @pytest.mark.unit
    def test_no_excellent_and_poor_contradiction_for_zone3(self, tmp_path):
        """A controlled Zone3 run must not simultaneously read
        aerobic_efficiency='Excellent aerobic base' and zone_distribution='Poor'."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 5.0, 2: 19.0, 3: 76.0}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        if result["aerobic_efficiency"].startswith("Excellent"):
            assert result["zone_distribution_rating"] != "Poor"
