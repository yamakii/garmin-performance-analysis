"""VDOT calculator based on Jack Daniels' Running Formula.

Implements the oxygen cost and %VO2max equations for:
- VDOT estimation from race performance
- Pace zone calculation
- Race time prediction
- HR zone derivation from lactate threshold
"""

from __future__ import annotations

import math

from garmin_mcp.training_plan.models import HRZones, PaceZones


class VDOTCalculator:
    """Calculator for VDOT and derived training paces."""

    @staticmethod
    def _oxygen_cost(velocity_m_per_min: float) -> float:
        """Calculate oxygen cost (ml/kg/min) at a given velocity.

        Args:
            velocity_m_per_min: Running velocity in meters per minute.

        Returns:
            Oxygen cost in ml/kg/min.
        """
        v = velocity_m_per_min
        return -4.60 + 0.182258 * v + 0.000104 * v * v

    @staticmethod
    def _percent_vo2max(time_minutes: float) -> float:
        """Calculate fraction of VO2max sustainable for given duration.

        Args:
            time_minutes: Duration in minutes.

        Returns:
            Fraction of VO2max (0-1 range).
        """
        t = time_minutes
        return (
            0.8
            + 0.1894393 * math.exp(-0.012778 * t)
            + 0.2989558 * math.exp(-0.1932605 * t)
        )

    @classmethod
    def vdot_from_race(cls, distance_km: float, time_seconds: int) -> float:
        """Calculate VDOT from a race performance.

        Args:
            distance_km: Race distance in kilometers.
            time_seconds: Finish time in seconds.

        Returns:
            VDOT value.
        """
        distance_m = distance_km * 1000.0
        time_min = time_seconds / 60.0
        velocity = distance_m / time_min  # m/min

        vo2 = cls._oxygen_cost(velocity)
        pct = cls._percent_vo2max(time_min)

        return vo2 / pct

    @classmethod
    def vdot_from_vo2max(cls, vo2max: float) -> float:
        """Convert Garmin VO2max value to approximate VDOT.

        Garmin's VO2max estimation is close to VDOT for trained runners.
        A small adjustment factor is applied.

        Args:
            vo2max: Garmin VO2max value (ml/kg/min).

        Returns:
            Approximate VDOT value.
        """
        # Garmin VO2max ≈ VDOT for most runners
        # Apply a minor scaling factor based on empirical observations
        return vo2max * 0.98

    @classmethod
    def pace_zones(cls, vdot: float) -> PaceZones:
        """Calculate Daniels training pace zones from VDOT.

        Based on Daniels' Running Formula tables:
        - Easy: 59-74% VO2max
        - Marathon: ~75-84% VO2max
        - Threshold: ~83-88% VO2max
        - Interval: ~95-100% VO2max
        - Repetition: ~105-110% VO2max (faster than VO2max pace)

        Args:
            vdot: VDOT value.

        Returns:
            PaceZones with paces in seconds per km.
        """

        # Calculate velocity (m/min) for each intensity as %VO2max
        def _velocity_for_pct(pct_vo2max: float) -> float:
            """Solve oxygen cost equation for velocity given %VO2max * VDOT."""
            target_vo2 = pct_vo2max * vdot
            # Solve: target_vo2 = -4.60 + 0.182258*v + 0.000104*v^2
            # 0.000104*v^2 + 0.182258*v + (-4.60 - target_vo2) = 0
            a = 0.000104
            b = 0.182258
            c = -4.60 - target_vo2
            discriminant = b * b - 4 * a * c
            if discriminant < 0:
                discriminant = 0
            v = (-b + math.sqrt(discriminant)) / (2 * a)
            return max(v, 1.0)

        def _pace_from_velocity(v_m_per_min: float) -> float:
            """Convert velocity (m/min) to pace (sec/km)."""
            return 1000.0 / v_m_per_min * 60.0

        # Daniels' intensity percentages
        easy_low_v = _velocity_for_pct(0.59)
        easy_high_v = _velocity_for_pct(0.74)
        marathon_v = _velocity_for_pct(0.80)
        threshold_v = _velocity_for_pct(0.88)
        interval_v = _velocity_for_pct(0.98)
        repetition_v = _velocity_for_pct(1.05)

        return PaceZones(
            easy_low=round(_pace_from_velocity(easy_low_v), 1),
            easy_high=round(_pace_from_velocity(easy_high_v), 1),
            marathon=round(_pace_from_velocity(marathon_v), 1),
            threshold=round(_pace_from_velocity(threshold_v), 1),
            interval=round(_pace_from_velocity(interval_v), 1),
            repetition=round(_pace_from_velocity(repetition_v), 1),
        )

    @classmethod
    def predict_race_time(cls, vdot: float, distance_km: float) -> int:
        """Predict race time from VDOT value.

        Uses binary search to find the time that produces the given VDOT
        for the specified distance.

        Args:
            vdot: VDOT value.
            distance_km: Target race distance in km.

        Returns:
            Predicted time in seconds.
        """
        # Binary search for the time
        low_sec = 1
        high_sec = 86400  # 24 hours max

        for _ in range(100):  # sufficient iterations for convergence
            mid_sec = (low_sec + high_sec) // 2
            estimated_vdot = cls.vdot_from_race(distance_km, mid_sec)

            if abs(estimated_vdot - vdot) < 0.01:
                return mid_sec
            elif estimated_vdot > vdot:
                # Running faster (less time) gives higher VDOT, need more time
                low_sec = mid_sec
            else:
                high_sec = mid_sec

        return (low_sec + high_sec) // 2

    @staticmethod
    def hr_zones_from_lt(lt_hr: int, max_hr: int | None = None) -> HRZones:
        """Calculate HR training zones from lactate threshold heart rate.

        Based on Daniels' framework:
        - Easy: 65-79% of LTHR
        - Marathon: 80-87% of LTHR
        - Threshold: 88-92% of LTHR (near LT)

        If max_hr is provided, zones are capped at max_hr.

        Args:
            lt_hr: Lactate threshold heart rate (bpm).
            max_hr: Optional maximum heart rate (bpm).

        Returns:
            HRZones with bpm values.
        """

        def _cap(hr: int) -> int:
            if max_hr is not None:
                return min(hr, max_hr)
            return hr

        return HRZones(
            easy_low=int(lt_hr * 0.65),
            easy_high=_cap(int(lt_hr * 0.79)),
            marathon_low=int(lt_hr * 0.80),
            marathon_high=_cap(int(lt_hr * 0.87)),
            threshold_low=int(lt_hr * 0.88),
            threshold_high=_cap(int(lt_hr * 0.92)),
        )
