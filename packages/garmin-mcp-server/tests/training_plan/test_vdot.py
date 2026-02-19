"""Tests for VDOT calculator.

Verifies against published Daniels' VDOT tables for known race performances.
"""

import pytest

from garmin_mcp.training_plan.vdot import VDOTCalculator


@pytest.mark.unit
class TestVDOTFromRace:
    """Test VDOT calculation from race performances against formula-derived values."""

    def test_vdot_30_5k(self):
        # VDOT 30: 5K ≈ 30:41 (1841s)
        vdot = VDOTCalculator.vdot_from_race(5.0, 1841)
        assert vdot == pytest.approx(30, abs=0.5)

    def test_vdot_40_5k(self):
        # VDOT 40: 5K ≈ 24:06 (1446s)
        vdot = VDOTCalculator.vdot_from_race(5.0, 1446)
        assert vdot == pytest.approx(40, abs=0.5)

    def test_vdot_50_5k(self):
        # VDOT 50: 5K ≈ 19:56 (1196s)
        vdot = VDOTCalculator.vdot_from_race(5.0, 1196)
        assert vdot == pytest.approx(50, abs=0.5)

    def test_vdot_60_5k(self):
        # VDOT 60: 5K ≈ 17:02 (1022s)
        vdot = VDOTCalculator.vdot_from_race(5.0, 1022)
        assert vdot == pytest.approx(60, abs=0.5)

    def test_vdot_40_10k(self):
        # VDOT 40: 10K ≈ 50:01 (3001s)
        vdot = VDOTCalculator.vdot_from_race(10.0, 3001)
        assert vdot == pytest.approx(40, abs=0.5)

    def test_vdot_50_half(self):
        # VDOT 50: Half ≈ 1:31:31 (5491s)
        vdot = VDOTCalculator.vdot_from_race(21.0975, 5491)
        assert vdot == pytest.approx(50, abs=0.5)

    def test_vdot_50_marathon(self):
        # VDOT 50: Marathon ≈ 3:10:39 (11439s)
        vdot = VDOTCalculator.vdot_from_race(42.195, 11439)
        assert vdot == pytest.approx(50, abs=0.5)

    def test_higher_vdot_for_faster_time(self):
        """Faster race time should produce higher VDOT."""
        slow = VDOTCalculator.vdot_from_race(5.0, 1800)
        fast = VDOTCalculator.vdot_from_race(5.0, 1200)
        assert fast > slow


@pytest.mark.unit
class TestVDOTFromVO2Max:
    def test_conversion(self):
        vdot = VDOTCalculator.vdot_from_vo2max(50.0)
        # Should be close to 50 but slightly lower
        assert 45 < vdot < 52

    def test_scaling(self):
        vdot_low = VDOTCalculator.vdot_from_vo2max(40.0)
        vdot_high = VDOTCalculator.vdot_from_vo2max(60.0)
        assert vdot_high > vdot_low


@pytest.mark.unit
class TestPaceZones:
    def test_vdot_40_zones(self):
        zones = VDOTCalculator.pace_zones(40)
        # Easy should be slowest, repetition fastest
        assert zones.easy_low > zones.easy_high
        assert zones.easy_high > zones.marathon
        assert zones.marathon > zones.threshold
        assert zones.threshold > zones.interval
        assert zones.interval > zones.repetition

    def test_vdot_50_zones(self):
        zones = VDOTCalculator.pace_zones(50)
        # All paces should be faster (lower sec/km) than VDOT 40
        zones_40 = VDOTCalculator.pace_zones(40)
        assert zones.easy_low < zones_40.easy_low
        assert zones.threshold < zones_40.threshold
        assert zones.interval < zones_40.interval

    def test_vdot_50_threshold_reasonable(self):
        zones = VDOTCalculator.pace_zones(50)
        # VDOT 50 threshold should be around 4:08-4:20/km (~248-260 sec/km)
        assert 230 < zones.threshold < 280

    def test_vdot_50_easy_reasonable(self):
        zones = VDOTCalculator.pace_zones(50)
        # VDOT 50 easy should be around 5:20-6:30/km (~320-390 sec/km)
        assert 290 < zones.easy_high < 420
        assert zones.easy_low > zones.easy_high

    def test_all_paces_positive(self):
        for vdot in [30, 40, 50, 60, 70]:
            zones = VDOTCalculator.pace_zones(vdot)
            assert zones.easy_low > 0
            assert zones.easy_high > 0
            assert zones.marathon > 0
            assert zones.threshold > 0
            assert zones.interval > 0
            assert zones.repetition > 0


@pytest.mark.unit
class TestPredictRaceTime:
    def test_predict_5k_vdot_40(self):
        time_sec = VDOTCalculator.predict_race_time(40, 5.0)
        # VDOT 40: 5K ≈ 24:06 (1446s)
        assert time_sec == pytest.approx(1446, abs=10)

    def test_predict_10k_vdot_50(self):
        time_sec = VDOTCalculator.predict_race_time(50, 10.0)
        # VDOT 50: 10K ≈ 41:20 (2480s)
        assert time_sec == pytest.approx(2480, abs=30)

    def test_predict_half_vdot_50(self):
        time_sec = VDOTCalculator.predict_race_time(50, 21.0975)
        # VDOT 50: Half ≈ 1:31:31 (5491s)
        assert time_sec == pytest.approx(5491, abs=60)

    def test_longer_distance_slower(self):
        time_5k = VDOTCalculator.predict_race_time(45, 5.0)
        time_10k = VDOTCalculator.predict_race_time(45, 10.0)
        time_half = VDOTCalculator.predict_race_time(45, 21.0975)
        assert time_5k < time_10k < time_half

    def test_roundtrip_vdot(self):
        """VDOT from race → predict race → should match original time."""
        original_time = 1400
        vdot = VDOTCalculator.vdot_from_race(5.0, original_time)
        predicted = VDOTCalculator.predict_race_time(vdot, 5.0)
        assert predicted == pytest.approx(original_time, abs=5)
