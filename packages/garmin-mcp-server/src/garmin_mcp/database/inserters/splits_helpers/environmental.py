"""Environmental conditions and impact calculations."""


class EnvironmentalCalculator:
    """Calculate environmental conditions and their impact on performance."""

    @staticmethod
    def calculate_environmental_conditions(
        temp: float | None, wind: float | None, humidity: float | None
    ) -> str | None:
        """
        Summarize environmental conditions.

        Args:
            temp: Temperature in Celsius
            wind: Wind speed in km/h
            humidity: Humidity percentage

        Returns:
            Environmental conditions summary or None
        """
        if temp is None:
            return None

        parts = []

        if temp < 10:
            parts.append(f"Cold ({int(temp)}°C)")
        elif 10 <= temp < 18:
            parts.append(f"Cool ({int(temp)}°C)")
        elif 18 <= temp < 25:
            parts.append(f"Mild ({int(temp)}°C)")
        else:  # 25+
            parts.append(f"Hot ({int(temp)}°C)")

        if wind is not None:
            if wind < 5:
                parts.append("Calm")
            elif 5 <= wind < 15:
                parts.append(f"Breezy ({int(wind)} km/h)")
            else:  # 15+
                parts.append(f"Windy ({int(wind)} km/h)")

        if humidity is not None:
            if humidity > 80:
                parts.append(f"Humid ({int(humidity)}%)")
            elif humidity < 30:
                parts.append(f"Dry ({int(humidity)}%)")

        return ", ".join(parts)

    @staticmethod
    def calculate_wind_impact(
        wind_speed: float | None, wind_dir: float | None = None
    ) -> str | None:
        """
        Evaluate wind impact on performance.

        Args:
            wind_speed: Wind speed in km/h
            wind_dir: Wind direction in degrees (0=N, 90=E, 180=S, 270=W)

        Returns:
            Wind impact evaluation or None
        """
        if wind_speed is None:
            return None

        if wind_speed < 5:
            return "Minimal (<5 km/h)"
        elif 5 <= wind_speed < 15:
            if wind_dir is not None:
                if wind_dir < 45 or wind_dir > 315:
                    return f"Moderate headwind ({int(wind_speed)} km/h)"
                elif 135 < wind_dir < 225:
                    return f"Moderate tailwind ({int(wind_speed)} km/h)"
                else:
                    return f"Moderate crosswind ({int(wind_speed)} km/h)"
            else:
                return f"Moderate ({int(wind_speed)} km/h)"
        else:  # 15+
            return f"Significant ({int(wind_speed)} km/h, pace impact expected)"

    @staticmethod
    def calculate_temp_impact(temp: float | None, training_type: str) -> str | None:
        """
        Evaluate temperature impact based on training intensity.

        Args:
            temp: Temperature in Celsius
            training_type: Training type (recovery, low_moderate, base, tempo_threshold, interval_sprint)

        Returns:
            Temperature impact evaluation or None
        """
        if temp is None:
            return None

        temp_int = int(temp)

        if training_type in ["recovery", "low_moderate"]:
            if 15 <= temp <= 22:
                return f"Good ({temp_int}°C)"
            elif 10 <= temp < 15 or 22 < temp <= 25:
                return f"Acceptable ({temp_int}°C)"
            elif temp < 10:
                return f"Cold ({temp_int}°C)"
            else:  # >25
                return f"Hot ({temp_int}°C)"

        elif training_type in ["base", "tempo_threshold"]:
            if 10 <= temp <= 18:
                return f"Ideal ({temp_int}°C)"
            elif 18 < temp <= 23:
                return f"Acceptable ({temp_int}°C)"
            elif temp < 10:
                return f"Cool ({temp_int}°C)"
            else:  # >23
                return f"Hot ({temp_int}°C, hydration important)"

        else:  # interval_sprint
            if 8 <= temp <= 15:
                return f"Ideal ({temp_int}°C)"
            elif 15 < temp <= 20:
                return f"Good ({temp_int}°C)"
            elif 20 < temp <= 25:
                return f"Warm ({temp_int}°C, performance may decrease)"
            elif temp < 8:
                return f"Cold ({temp_int}°C, longer warmup needed)"
            else:  # >25
                return f"Too hot ({temp_int}°C, consider rescheduling)"

    @staticmethod
    def calculate_environmental_impact(
        temp_impact: str | None,
        wind_impact: str | None,
        elevation_gain: float | None,
        elevation_loss: float | None,
    ) -> str:
        """
        Calculate overall environmental impact rating.

        Args:
            temp_impact: Temperature impact string
            wind_impact: Wind impact string
            elevation_gain: Elevation gain in meters
            elevation_loss: Elevation loss in meters

        Returns:
            Overall environmental impact rating
        """
        challenge_score = 0

        if temp_impact:
            if "Too hot" in temp_impact or "Cold" in temp_impact:
                challenge_score += 3
            elif "Hot" in temp_impact or "Cool" in temp_impact:
                challenge_score += 2
            elif "Warm" in temp_impact:
                challenge_score += 1

        if wind_impact:
            if "Significant" in wind_impact:
                challenge_score += 2
            elif "Moderate" in wind_impact:
                challenge_score += 1

        total_elevation = abs(elevation_gain or 0) + abs(elevation_loss or 0)
        if total_elevation > 100:
            challenge_score += 2
        elif total_elevation > 50:
            challenge_score += 1

        if challenge_score == 0:
            return "Ideal conditions"
        elif challenge_score <= 2:
            return "Good conditions"
        elif challenge_score <= 4:
            return "Moderate challenge"
        elif challenge_score <= 5:
            return "Challenging conditions"
        else:  # 6-7
            return "Extreme conditions"
