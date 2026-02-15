"""Heart rate zone calculation."""


class HRCalculator:
    """Calculate heart rate zones from HR values."""

    @staticmethod
    def calculate_hr_zone(heart_rate: float | None, hr_zones: list[dict]) -> str | None:
        """
        Map heart_rate to zone name using zone boundaries.

        Args:
            heart_rate: Heart rate in bpm
            hr_zones: List of zone dicts with zone_number, lower_bpm, upper_bpm

        Returns:
            Zone name (e.g., "Zone 2") or None
        """
        if heart_rate is None:
            return None

        if not hr_zones:
            return None

        for zone in hr_zones:
            zone_num = zone.get("zone_number")
            lower = zone.get("lower_bpm")
            upper = zone.get("upper_bpm")

            if lower is None or upper is None:
                continue

            if lower <= heart_rate <= upper:
                return f"Zone {zone_num}"

        first_zone_lower = hr_zones[0].get("lower_bpm")
        last_zone_upper = hr_zones[-1].get("upper_bpm")

        if first_zone_lower and heart_rate < first_zone_lower:
            return "Zone 0 (Recovery)"
        elif last_zone_upper and heart_rate > last_zone_upper:
            return "Zone 5+ (Max)"

        return None
