"""Calculate recommended paces and HR targets for next run based on current fitness.

Design principles (from evaluation-principles.md):
- Easy runs use HR ranges, not pace targets (pace is reference only)
- Recommendations are presented as ranges
- Include one adjustment tip (heat, fatigue)
- Include success criterion for self-evaluation
"""

import logging
from typing import Any

from garmin_mcp.reporting.components.formatting import format_pace

logger = logging.getLogger(__name__)

# Training types that map to "easy" recommendations
_EASY_TYPES = {"recovery", "aerobic_base", "aerobic_endurance"}
# Training types that map to "tempo" recommendations
_TEMPO_TYPES = {"tempo", "lactate_threshold"}
# Training types that map to "interval" recommendations
_INTERVAL_TYPES = {"vo2max", "anaerobic_capacity", "speed", "interval_training"}


class NextRunCalculator:
    """Calculate recommended paces for next run based on current fitness."""

    def calculate_easy_pace(
        self,
        hr_zones: dict[str, Any],
        pace_hr_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Estimate pace that would yield ~60% Zone 2 time.

        Easy run recommendations are HR-based (pace is reference only),
        per evaluation-principles.md.

        Args:
            hr_zones: HR zone boundaries from Garmin native zones.
            pace_hr_history: List of {pace_seconds_per_km, avg_hr} dicts
                from recent activities.

        Returns:
            Dict with target HR range, optional reference pace, success
            criterion, and adjustment tip.
        """
        zone_boundaries = hr_zones.get("zone_boundaries", [])
        zone_2 = next((z for z in zone_boundaries if z.get("zone_number") == 2), None)

        if not zone_2:
            return {
                "recommendation_type": "hr_based",
                "insufficient_data": True,
                "summary_ja": "HR zone データが不足しているため推奨値を算出できません。",
            }

        zone_2_low = zone_2["zone_low_boundary"]
        zone_2_high = zone_2["zone_high_boundary"]

        # Target the middle-to-upper portion of Zone 2 for easy runs
        # This aims for a HR that keeps most time in Zone 2
        target_hr_low = zone_2_low
        target_hr_high = zone_2_high

        result: dict[str, Any] = {
            "recommendation_type": "hr_based",
            "target_hr_low": target_hr_low,
            "target_hr_high": target_hr_high,
            "success_criterion": "Zone 2 比率 60% 以上で成功",
            "adjustment_tip": "暑い日は +5bpm 許容、疲労時は上限を 5bpm 下げる",
        }

        # If we have pace-HR history, estimate reference pace
        if pace_hr_history:
            reference = self._estimate_pace_for_hr_range(
                pace_hr_history, target_hr_low, target_hr_high
            )
            result["reference_pace_low"] = reference.get("pace_low")
            result["reference_pace_high"] = reference.get("pace_high")
            pace_low = reference.get("pace_low")
            pace_high = reference.get("pace_high")
            if pace_low is not None:
                result["reference_pace_low_formatted"] = format_pace(pace_low)
            if pace_high is not None:
                result["reference_pace_high_formatted"] = format_pace(pace_high)
        else:
            result["reference_pace_low"] = None
            result["reference_pace_high"] = None

        return result

    def calculate_tempo_pace(
        self, lactate_threshold: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Calculate tempo zone from LT data.

        Tempo range is LT pace +/- 5%.

        Args:
            lactate_threshold: Dict with speed_mps and heart_rate from LT test.

        Returns:
            Dict with target pace range and HR reference.
        """
        if not lactate_threshold:
            return {
                "insufficient_data": True,
                "target_pace_low": None,
                "summary_ja": "乳酸閾値データが不足しているため推奨値を算出できません。",
            }

        speed_mps = lactate_threshold.get("speed_mps")
        if not speed_mps or speed_mps <= 0:
            return {
                "insufficient_data": True,
                "target_pace_low": None,
                "summary_ja": "乳酸閾値の速度データが不足しているため推奨値を算出できません。",
            }

        # LT pace in seconds per km
        lt_pace = 1000.0 / speed_mps

        # Tempo range: 95% to 105% of LT pace
        # Lower value = faster (95% of LT pace time = running faster)
        # Higher value = slower (105% of LT pace time = running slower)
        target_pace_low = lt_pace * 0.95  # faster end
        target_pace_high = lt_pace * 1.05  # slower end

        result: dict[str, Any] = {
            "target_pace_low": target_pace_low,
            "target_pace_high": target_pace_high,
            "target_pace_low_formatted": format_pace(target_pace_low),
            "target_pace_high_formatted": format_pace(target_pace_high),
            "success_criterion": (
                f"ペース変動係数 (CV) < 0.03 かつ "
                f"{format_pace(target_pace_low)}~{format_pace(target_pace_high)} 維持で成功"
            ),
            "adjustment_tip": "暑い日は 5-10秒/km 遅めを許容",
        }

        hr = lactate_threshold.get("heart_rate")
        if hr:
            result["target_hr"] = hr

        return result

    def calculate_interval_pace(self, vo2_max: dict[str, Any] | None) -> dict[str, Any]:
        """Calculate interval pace from VO2max data.

        Uses VDOT-based estimation: vVO2max (km/h) ~ VO2max / 3.5
        Interval range is 95-100% of vVO2max pace.

        Args:
            vo2_max: Dict with precise_value from VO2max measurement.

        Returns:
            Dict with target interval pace range.
        """
        if not vo2_max:
            return {
                "insufficient_data": True,
                "target_pace_low": None,
                "summary_ja": "VO2max データが不足しているため推奨値を算出できません。",
            }

        vo2_value = vo2_max.get("precise_value")
        if not vo2_value or vo2_value <= 0:
            return {
                "insufficient_data": True,
                "target_pace_low": None,
                "summary_ja": "VO2max の値が不足しているため推奨値を算出できません。",
            }

        # vVO2max speed in km/h
        v_vo2max_kmh = vo2_value / 3.5
        # Convert to seconds per km
        v_vo2max_pace = 3600.0 / v_vo2max_kmh

        # Interval range: 95-100% of vVO2max
        # 100% vVO2max = the vVO2max pace itself (fastest)
        # 95% vVO2max speed = slightly slower pace
        target_pace_low = v_vo2max_pace  # fastest (100% vVO2max)
        target_pace_high = v_vo2max_pace / 0.95 * 1.0  # 95% speed = slower pace
        # 95% of speed means pace * (1/0.95)
        target_pace_high = v_vo2max_pace / 0.95

        result: dict[str, Any] = {
            "target_pace_low": target_pace_low,
            "target_pace_high": target_pace_high,
            "target_pace_low_formatted": format_pace(target_pace_low),
            "target_pace_high_formatted": format_pace(target_pace_high),
            "success_criterion": (
                f"Work 区間を {format_pace(target_pace_low)}~"
                f"{format_pace(target_pace_high)} で維持し、"
                f"Recovery で HR が Zone 2 まで回復すれば成功"
            ),
            "adjustment_tip": "疲労時は本数を減らして質を維持",
        }

        return result

    def recommend(
        self,
        training_type: str,
        hr_zones: dict[str, Any] | None = None,
        pace_hr_history: list[dict[str, Any]] | None = None,
        lactate_threshold: dict[str, Any] | None = None,
        vo2_max: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return next run recommendation based on current activity type.

        Routes to the appropriate calculator based on training type, then
        wraps the result with a Japanese summary.

        Args:
            training_type: Current activity's training type.
            hr_zones: HR zone boundaries (for easy recommendations).
            pace_hr_history: Recent pace-HR pairs (for easy recommendations).
            lactate_threshold: LT data (for tempo recommendations).
            vo2_max: VO2max data (for interval recommendations).

        Returns:
            Dict with recommended_type, targets, summary_ja, and details.
        """
        if training_type in _EASY_TYPES:
            return self._recommend_easy(hr_zones, pace_hr_history)
        elif training_type in _TEMPO_TYPES:
            return self._recommend_tempo(lactate_threshold)
        elif training_type in _INTERVAL_TYPES:
            return self._recommend_interval(vo2_max)
        else:
            # Unknown type: default to easy
            return self._recommend_easy(hr_zones, pace_hr_history)

    def _recommend_easy(
        self,
        hr_zones: dict[str, Any] | None,
        pace_hr_history: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build easy run recommendation."""
        if not hr_zones:
            return {
                "recommended_type": "easy",
                "insufficient_data": True,
                "summary_ja": "HR zone データが不足しているため、"
                "次回の Easy Run では体感で楽に感じるペースを維持してください。",
            }

        calc = self.calculate_easy_pace(hr_zones, pace_hr_history or [])

        # Build Japanese summary
        hr_low = calc.get("target_hr_low", "?")
        hr_high = calc.get("target_hr_high", "?")
        pace_low_fmt = calc.get("reference_pace_low_formatted")
        pace_high_fmt = calc.get("reference_pace_high_formatted")

        if pace_low_fmt and pace_high_fmt:
            summary = (
                f"次の Easy Run では HR {hr_low}-{hr_high} bpm を維持"
                f"（参考ペース {pace_low_fmt}~{pace_high_fmt}）。"
                f"{calc.get('success_criterion', '')}"
            )
        else:
            summary = (
                f"次の Easy Run では HR {hr_low}-{hr_high} bpm を維持。"
                f"{calc.get('success_criterion', '')}"
            )

        result = {
            "recommended_type": "easy",
            "summary_ja": summary,
        }
        # Merge calculator results
        result.update(calc)
        return result

    def _recommend_tempo(
        self, lactate_threshold: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Build tempo run recommendation."""
        calc = self.calculate_tempo_pace(lactate_threshold)

        if calc.get("insufficient_data"):
            return {
                "recommended_type": "tempo",
                "insufficient_data": True,
                "summary_ja": calc.get(
                    "summary_ja",
                    "乳酸閾値データが不足しているため推奨ペースを算出できません。",
                ),
            }

        pace_low_fmt = calc["target_pace_low_formatted"]
        pace_high_fmt = calc["target_pace_high_formatted"]
        hr_text = ""
        if calc.get("target_hr"):
            hr_text = f"（目標 HR ~{calc['target_hr']} bpm）"

        summary = (
            f"次のテンポ走では {pace_low_fmt}~{pace_high_fmt} を維持{hr_text}。"
            f"{calc.get('success_criterion', '')}"
        )

        result = {
            "recommended_type": "tempo",
            "summary_ja": summary,
        }
        result.update(calc)
        return result

    def _recommend_interval(self, vo2_max: dict[str, Any] | None) -> dict[str, Any]:
        """Build interval recommendation."""
        calc = self.calculate_interval_pace(vo2_max)

        if calc.get("insufficient_data"):
            return {
                "recommended_type": "interval",
                "insufficient_data": True,
                "summary_ja": calc.get(
                    "summary_ja",
                    "VO2max データが不足しているため推奨ペースを算出できません。",
                ),
            }

        pace_low_fmt = calc["target_pace_low_formatted"]
        pace_high_fmt = calc["target_pace_high_formatted"]

        summary = (
            f"次のインターバルでは Work 区間を "
            f"{pace_low_fmt}~{pace_high_fmt} で実施。"
            f"{calc.get('success_criterion', '')}"
        )

        result = {
            "recommended_type": "interval",
            "summary_ja": summary,
        }
        result.update(calc)
        return result

    @staticmethod
    def _estimate_pace_for_hr_range(
        pace_hr_history: list[dict[str, Any]],
        target_hr_low: int,
        target_hr_high: int,
    ) -> dict[str, float | None]:
        """Estimate pace range that corresponds to a target HR range.

        Uses linear interpolation from pace-HR history data points.

        Args:
            pace_hr_history: List of {pace_seconds_per_km, avg_hr} dicts.
            target_hr_low: Lower HR boundary.
            target_hr_high: Upper HR boundary.

        Returns:
            Dict with pace_low and pace_high (seconds/km), or None if
            cannot estimate.
        """
        if len(pace_hr_history) < 1:
            return {"pace_low": None, "pace_high": None}

        # Sort by HR ascending
        sorted_data = sorted(pace_hr_history, key=lambda x: x["avg_hr"])
        hrs = [d["avg_hr"] for d in sorted_data]
        paces = [d["pace_seconds_per_km"] for d in sorted_data]

        def interpolate_pace(target_hr: float) -> float | None:
            """Linear interpolation of pace for a given HR."""
            if len(hrs) == 1:
                # Single data point: return that pace as estimate
                return float(paces[0])

            # Clamp to data range
            if target_hr <= hrs[0]:
                return float(paces[0])
            if target_hr >= hrs[-1]:
                return float(paces[-1])

            # Find bracketing points
            for i in range(len(hrs) - 1):
                if hrs[i] <= target_hr <= hrs[i + 1]:
                    # Linear interpolation
                    hr_frac = (target_hr - hrs[i]) / (hrs[i + 1] - hrs[i])
                    return float(paces[i] + hr_frac * (paces[i + 1] - paces[i]))

            return float(paces[-1])

        pace_at_low_hr = interpolate_pace(target_hr_low)
        pace_at_high_hr = interpolate_pace(target_hr_high)

        if pace_at_low_hr is None or pace_at_high_hr is None:
            return {"pace_low": None, "pace_high": None}

        # Higher HR -> faster pace (lower number), but we want
        # pace_low < pace_high (slower number = higher sec/km)
        # Since HR correlates inversely with pace (higher HR = faster = lower sec/km),
        # pace_at_high_hr should be faster (lower) and pace_at_low_hr slower (higher)
        pace_fast = min(pace_at_low_hr, pace_at_high_hr)
        pace_slow = max(pace_at_low_hr, pace_at_high_hr)

        return {"pace_low": pace_fast, "pace_high": pace_slow}
