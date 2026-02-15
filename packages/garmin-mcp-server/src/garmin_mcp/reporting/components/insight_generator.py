"""Insight generation components extracted from ReportGeneratorWorker."""

import re
from typing import Any


class InsightGenerator:
    """Generates workout insights from comparison data."""

    def generate_workout_insight(
        self, similar_workouts: dict[str, Any], training_type: str
    ) -> str:
        """
        Generate workout insight based on comparison data and training type.

        Args:
            similar_workouts: Similar workouts comparison data
            training_type: Training type (aerobic_base, lactate_threshold, etc.)

        Returns:
            Insight text with efficiency improvement percentage
        """
        if not similar_workouts or "comparisons" not in similar_workouts:
            return "データ不足のため算出不可"

        comparisons = {comp["metric"]: comp for comp in similar_workouts["comparisons"]}

        # Base run pattern: Pace faster + Power lower = Efficiency improvement
        if training_type in ["aerobic_base", "recovery"]:
            pace_comp = comparisons.get("平均ペース")
            power_comp = comparisons.get("平均パワー")

            if pace_comp and power_comp:
                pace_change = self.extract_numeric_change(pace_comp["change"])
                power_change = self.extract_numeric_change(power_comp["change"])

                if pace_change < 0 and power_change < 0:  # Faster pace, lower power
                    avg_power = self.extract_numeric_value(power_comp["average"])
                    if avg_power and avg_power > 0:
                        efficiency_pct = abs(power_change / avg_power * 100)
                        return f"ペース{abs(pace_change):.0f}秒速いのにパワー{abs(power_change):.0f}W低下＝**効率が{efficiency_pct:.1f}%向上** ✅"

        # Interval pattern: Multiple metrics improvement
        elif training_type in [
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        ]:
            improvements = []
            pace_comp = comparisons.get("Work平均ペース")
            power_comp = comparisons.get("Work平均パワー")
            stride_comp = comparisons.get("Work平均ストライド")

            if pace_comp and self.extract_numeric_change(pace_comp["change"]) < 0:
                pace_change = abs(self.extract_numeric_change(pace_comp["change"]))
                improvements.append(f"Workペース+{pace_change:.0f}秒速")

            if power_comp and self.extract_numeric_change(power_comp["change"]) > 0:
                power_change = self.extract_numeric_change(power_comp["change"])
                improvements.append(f"パワー+{power_change:.0f}W")

            if stride_comp and self.extract_numeric_change(stride_comp["change"]) > 0:
                stride_change = self.extract_numeric_change(stride_comp["change"])
                improvements.append(f"ストライド+{stride_change * 100:.0f}cm向上")

            if improvements:
                improvements_text = "、".join(improvements)
                return f"{improvements_text} = **高強度下でもフォーム効率とパワー出力を改善** ✅"

        # Threshold pattern: Same pace + Lower HR = Efficiency improvement
        elif training_type in ["lactate_threshold", "tempo"]:
            pace_comp = comparisons.get("メイン平均ペース")
            hr_comp = comparisons.get("メイン平均心拍")

            if pace_comp and hr_comp:
                pace_change = self.extract_numeric_change(pace_comp["change"])
                hr_change = self.extract_numeric_change(hr_comp["change"])

                if abs(pace_change) <= 1 and hr_change < 0:  # Same pace, lower HR
                    avg_hr = self.extract_numeric_value(hr_comp["average"])
                    if avg_hr and avg_hr > 0:
                        efficiency_pct = abs(hr_change / avg_hr * 100)
                        return f"同じペースで心拍{abs(hr_change):.0f}bpm低下 = **閾値での効率が{efficiency_pct:.1f}%向上** ✅"

        # Fallback: Generic improvement message
        return "複数指標で改善が見られます"

    def extract_numeric_change(self, change_text: str) -> float:
        """
        Extract numeric change from comparison text.

        Examples:
            "+3秒速い" -> -3 (faster is negative)
            "-4 bpm" -> -4
            "+7 W" -> +7
            "+0.03 m" -> +0.03

        Args:
            change_text: Change text from comparison

        Returns:
            Numeric change value (negative for improvements in pace/HR)
        """
        # Extract number with optional sign
        match = re.search(r"([+-]?\d+\.?\d*)", change_text)
        if not match:
            return 0.0

        value = float(match.group(1))

        # Invert sign for "速い" (faster is better, so negative)
        if "速い" in change_text:
            value = -abs(value)

        return value

    def extract_numeric_value(self, value_text: str) -> float | None:
        """
        Extract numeric value from text.

        Examples:
            "230 W" -> 230.0
            "171 bpm" -> 171.0
            "6:48/km" -> None (not a simple number)

        Args:
            value_text: Value text

        Returns:
            Numeric value or None
        """
        match = re.search(r"(\d+\.?\d*)", value_text)
        if match:
            return float(match.group(1))
        return None

    def generate_reference_info(
        self,
        vo2_max_data: dict[str, Any] | None,
        lactate_threshold_data: dict[str, Any] | None,
        training_type: str = "aerobic_base",
    ) -> str:
        """
        Generate reference information text for VO2 Max and lactate threshold.

        Args:
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database
            training_type: Training type (used to determine if FTP should be shown)

        Returns:
            Formatted reference info text
        """
        parts: list[str] = []

        # VO2 Max
        if vo2_max_data:
            vo2_value = vo2_max_data.get("precise_value") or vo2_max_data.get("value")
            vo2_category = vo2_max_data.get("category")
            if vo2_value:
                if vo2_category and vo2_category != 0 and vo2_category != "N/A":
                    parts.append(f"VO2 Max {vo2_value} ml/kg/min（{vo2_category}）")
                else:
                    parts.append(f"VO2 Max {vo2_value} ml/kg/min")

        # Lactate threshold pace
        if lactate_threshold_data:
            threshold_speed = lactate_threshold_data.get("speed_mps")
            if threshold_speed and threshold_speed > 0:
                pace_seconds_per_km = 1000 / threshold_speed
                pace_min = int(pace_seconds_per_km // 60)
                pace_sec = int(pace_seconds_per_km % 60)
                parts.append(f"閾値ペース {pace_min}:{pace_sec:02d}/km")

            # Add FTP for Interval/High Intensity activities
            if training_type in ["interval_training", "high_intensity"]:
                ftp = lactate_threshold_data.get("functional_threshold_power")
                if ftp:
                    parts.append(f"FTP {int(ftp)}W")

        if parts:
            return "> **参考**: " + "、".join(parts)
        return ""
