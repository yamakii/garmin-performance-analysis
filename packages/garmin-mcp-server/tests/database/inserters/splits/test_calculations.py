"""Per-split calculations: HR-zone mapping, cadence rating, power efficiency, environmental / wind / temperature impact."""

import pytest

from garmin_mcp.database.inserters.splits_helpers.cadence_power import (
    CadencePowerCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.environmental import (
    EnvironmentalCalculator,
)
from garmin_mcp.database.inserters.splits_helpers.hr_calculations import HRCalculator


class TestSplitCalculations:
    @pytest.mark.unit
    def test_calculate_hr_zone_mapping(self):
        """Test HR zone calculation from heart rate value.

        RED Phase: This test will fail because _calculate_hr_zone doesn't exist yet.
        """

        # Test data: Typical HR zones for a runner
        hr_zones = [
            {"zone_number": 1, "lower_bpm": 100, "upper_bpm": 120},
            {"zone_number": 2, "lower_bpm": 120, "upper_bpm": 150},
            {"zone_number": 3, "lower_bpm": 150, "upper_bpm": 165},
            {"zone_number": 4, "lower_bpm": 165, "upper_bpm": 180},
            {"zone_number": 5, "lower_bpm": 180, "upper_bpm": 195},
        ]

        # Test zone mapping
        assert HRCalculator.calculate_hr_zone(110, hr_zones) == "Zone 1"
        assert HRCalculator.calculate_hr_zone(145, hr_zones) == "Zone 2"
        assert HRCalculator.calculate_hr_zone(160, hr_zones) == "Zone 3"
        assert HRCalculator.calculate_hr_zone(170, hr_zones) == "Zone 4"
        assert HRCalculator.calculate_hr_zone(185, hr_zones) == "Zone 5"

        # Test edge cases
        assert (
            HRCalculator.calculate_hr_zone(95, hr_zones) == "Zone 0 (Recovery)"
        )  # Below Zone 1
        assert (
            HRCalculator.calculate_hr_zone(200, hr_zones) == "Zone 5+ (Max)"
        )  # Above Zone 5

        # Test boundary values
        assert HRCalculator.calculate_hr_zone(120, hr_zones) in [
            "Zone 1",
            "Zone 2",
        ]  # Boundary

        # Test None handling
        assert HRCalculator.calculate_hr_zone(None, hr_zones) is None

    @pytest.mark.unit
    def test_calculate_cadence_rating(self):
        """Test cadence rating evaluation.

        RED Phase: This test will fail because _calculate_cadence_rating doesn't exist yet.
        """

        # Test ratings based on scientific thresholds
        assert (
            CadencePowerCalculator.calculate_cadence_rating(165)
            == "Low (165 spm, target 180+)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(175) == "Good (175 spm)"
        assert (
            CadencePowerCalculator.calculate_cadence_rating(185)
            == "Excellent (185 spm)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(192) == "Elite (192 spm)"

        # Test boundary values
        assert CadencePowerCalculator.calculate_cadence_rating(170) == "Good (170 spm)"
        assert (
            CadencePowerCalculator.calculate_cadence_rating(180)
            == "Excellent (180 spm)"
        )
        assert CadencePowerCalculator.calculate_cadence_rating(190) == "Elite (190 spm)"

        # Test None handling
        assert CadencePowerCalculator.calculate_cadence_rating(None) is None

    @pytest.mark.unit
    def test_calculate_power_efficiency(self):
        """Test power efficiency (W/kg) calculation."""

        # Test various power/weight ratios
        # 170/70 = 2.43 (Low, <2.5)
        # 200/70 = 2.86 (Moderate, 2.5-3.5)
        # 250/70 = 3.57 (Good, 3.5-4.5)
        # 350/70 = 5.0 (Excellent, >=4.5)
        assert (
            CadencePowerCalculator.calculate_power_efficiency(170, 70)
            == "Low (2.4 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(200, 70)
            == "Moderate (2.9 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(250, 70)
            == "Good (3.6 W/kg)"
        )
        assert (
            CadencePowerCalculator.calculate_power_efficiency(350, 70)
            == "Excellent (5.0 W/kg)"
        )

        # Test None handling
        assert CadencePowerCalculator.calculate_power_efficiency(None, 70) is None
        assert CadencePowerCalculator.calculate_power_efficiency(250, None) is None
        assert CadencePowerCalculator.calculate_power_efficiency(None, None) is None

    @pytest.mark.unit
    def test_calculate_environmental_conditions(self):
        """Test environmental conditions summary."""

        # Test various conditions
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(15, 2, 65)
            == "Cool (15°C), Calm"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(28, 12, 85)
            == "Hot (28°C), Breezy (12 km/h), Humid (85%)"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(8, 20, 25)
            == "Cold (8°C), Windy (20 km/h), Dry (25%)"
        )
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(20, None, None)
            == "Mild (20°C)"
        )

        # Test None handling
        assert (
            EnvironmentalCalculator.calculate_environmental_conditions(None, 10, 50)
            is None
        )

    @pytest.mark.unit
    def test_calculate_wind_impact(self):
        """Test wind impact evaluation."""

        # Test wind levels
        assert EnvironmentalCalculator.calculate_wind_impact(3) == "Minimal (<5 km/h)"
        assert (
            EnvironmentalCalculator.calculate_wind_impact(10, None)
            == "Moderate (10 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(20)
            == "Significant (20 km/h, pace impact expected)"
        )

        # Test with direction (headwind/tailwind/crosswind)
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 30)
            == "Moderate headwind (12 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 180)
            == "Moderate tailwind (12 km/h)"
        )
        assert (
            EnvironmentalCalculator.calculate_wind_impact(12, 90)
            == "Moderate crosswind (12 km/h)"
        )

        # Test None handling
        assert EnvironmentalCalculator.calculate_wind_impact(None) is None

    @pytest.mark.unit
    def test_calculate_temp_impact(self):
        """Test temperature impact based on training type."""

        # Test recovery/low_moderate (wider tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(18, "recovery")
            == "Good (18°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(28, "low_moderate")
            == "Hot (28°C)"
        )

        # Test base/tempo_threshold (moderate tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(15, "tempo_threshold")
            == "Ideal (15°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(25, "tempo_threshold")
            == "Hot (25°C, hydration important)"
        )

        # Test interval_sprint (narrow tolerance)
        assert (
            EnvironmentalCalculator.calculate_temp_impact(12, "interval_sprint")
            == "Ideal (12°C)"
        )
        assert (
            EnvironmentalCalculator.calculate_temp_impact(28, "interval_sprint")
            == "Too hot (28°C, consider rescheduling)"
        )

        # Test None handling
        assert EnvironmentalCalculator.calculate_temp_impact(None, "base") is None

    @pytest.mark.unit
    def test_calculate_environmental_impact(self):
        """Test overall environmental impact rating."""

        # Test ideal conditions (score=0)
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Ideal (15°C)", "Minimal (<5 km/h)", 3, 2
            )
            == "Ideal conditions"
        )

        # Test good conditions (score=1-2: Warm(1) + no wind + 30m elevation(0))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Warm (22°C)", "Minimal (<5 km/h)", 15, 15
            )
            == "Good conditions"
        )

        # Test moderate challenge (score=3-4: Hot(2) + Moderate(1) + 40m elevation(0))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Hot (25°C)", "Moderate (10 km/h)", 20, 20
            )
            == "Moderate challenge"
        )

        # Test challenging conditions (score=5: Hot(2) + Moderate(1) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Hot (26°C)", "Moderate headwind (12 km/h)", 60, 60
            )
            == "Challenging conditions"
        )

        # Test extreme conditions (score=6: Too hot(3) + Moderate(1) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Too hot (28°C)", "Moderate (12 km/h)", 60, 60
            )
            == "Extreme conditions"
        )

        # Test extreme conditions (score=7: Too hot(3) + Significant(2) + 120m elevation(2))
        assert (
            EnvironmentalCalculator.calculate_environmental_impact(
                "Too hot (30°C)", "Significant (20 km/h)", 100, 100
            )
            == "Extreme conditions"
        )
