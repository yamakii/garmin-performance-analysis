"""Cadence rating and power efficiency calculations."""


class CadencePowerCalculator:
    """Calculate cadence ratings and power efficiency metrics."""

    @staticmethod
    def calculate_cadence_rating(cadence: float | None) -> str | None:
        """
        Evaluate cadence quality based on running science.

        Args:
            cadence: Cadence in steps per minute (spm)

        Returns:
            Cadence rating string or None
        """
        if cadence is None:
            return None

        cadence_int = int(cadence)

        if cadence < 170:
            return f"Low ({cadence_int} spm, target 180+)"
        elif 170 <= cadence < 180:
            return f"Good ({cadence_int} spm)"
        elif 180 <= cadence < 190:
            return f"Excellent ({cadence_int} spm)"
        else:  # 190+
            return f"Elite ({cadence_int} spm)"

    @staticmethod
    def calculate_power_efficiency(
        power: float | None, weight_kg: float | None
    ) -> str | None:
        """
        Calculate power-to-weight ratio (W/kg).

        Args:
            power: Power in watts
            weight_kg: Body weight in kg

        Returns:
            Power efficiency rating or None
        """
        if power is None or weight_kg is None:
            return None

        w_per_kg = power / weight_kg

        if w_per_kg < 2.5:
            return f"Low ({w_per_kg:.1f} W/kg)"
        elif 2.5 <= w_per_kg < 3.5:
            return f"Moderate ({w_per_kg:.1f} W/kg)"
        elif 3.5 <= w_per_kg < 4.5:
            return f"Good ({w_per_kg:.1f} W/kg)"
        else:  # 4.5+
            return f"Excellent ({w_per_kg:.1f} W/kg)"
