"""Chart generation components extracted from ReportGeneratorWorker."""

import logging
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generates Mermaid chart data from activity splits and metrics."""

    def __init__(self, db_reader: GarminDBReader) -> None:
        self.db_reader = db_reader

    def generate_mermaid_data(
        self, splits: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """
        Generate Mermaid graph data from splits.

        Args:
            splits: List of split dictionaries

        Returns:
            Dictionary with Mermaid graph data or None if no splits
        """
        if not splits:
            return None

        # Extract data from splits
        x_axis_labels = [f"{s['index']}" for s in splits]
        pace_data = [s["pace_seconds_per_km"] for s in splits]
        heart_rate_data = [s["heart_rate"] for s in splits]
        power_data = [s.get("power", 0) or 0 for s in splits]  # Handle None values

        # Calculate dynamic Y-axis ranges with 10% padding
        if pace_data:
            pace_min = min(pace_data) * 0.9
            pace_max = max(pace_data) * 1.1
        else:
            pace_min = pace_max = 0

        if heart_rate_data:
            hr_min = min(heart_rate_data) * 0.9
            hr_max = max(heart_rate_data) * 1.1
        else:
            hr_min = hr_max = 0

        return {
            "x_axis_labels": x_axis_labels,
            "pace_data": pace_data,
            "heart_rate_data": heart_rate_data,
            "power_data": power_data,
            "pace_min": round(pace_min, 1),
            "pace_max": round(pace_max, 1),
            "hr_min": round(hr_min, 1),
            "hr_max": round(hr_max, 1),
        }

    def generate_mermaid_analysis(
        self, splits: list[dict[str, Any]], training_type_category: str
    ) -> str | None:
        """
        Generate Work/Recovery transition analysis for interval workouts.

        Args:
            splits: List of split dictionaries with intensity_type
            training_type_category: Training type category

        Returns:
            3-4 bullet point analysis text (Japanese) or None for non-interval
        """
        if training_type_category != "interval_sprint":
            return None

        # Extract Work and Recovery segments
        work_splits = [
            s for s in splits if s.get("intensity_type") in ["INTERVAL", "active"]
        ]
        recovery_splits = [
            s for s in splits if s.get("intensity_type") in ["RECOVERY", "rest"]
        ]

        if not work_splits:
            return None

        # Calculate Work metrics
        work_pace_avg = sum(s["pace_seconds_per_km"] for s in work_splits) / len(
            work_splits
        )
        work_hr_avg = sum(s["heart_rate"] for s in work_splits) / len(work_splits)
        work_power_avg = (
            sum(s.get("power", 0) or 0 for s in work_splits) / len(work_splits)
            if any(s.get("power") for s in work_splits)
            else None
        )

        # Calculate Recovery metrics (if exist)
        if recovery_splits:
            recovery_pace_avg = sum(
                s["pace_seconds_per_km"] for s in recovery_splits
            ) / len(recovery_splits)
            recovery_hr_avg = sum(s["heart_rate"] for s in recovery_splits) / len(
                recovery_splits
            )
        else:
            recovery_pace_avg = None
            recovery_hr_avg = None

        # Format pace
        work_pace_min = int(work_pace_avg // 60)
        work_pace_sec = int(work_pace_avg % 60)
        work_pace_str = f"{work_pace_min}:{work_pace_sec:02d}/km"

        # Build analysis bullets
        bullets = []

        # Bullet 1: Work segments overview
        bullets.append(
            f"- Work区間{len(work_splits)}本: 平均ペース{work_pace_str}、"
            f"平均心拍{work_hr_avg:.0f}bpm"
            + (f"、平均パワー{work_power_avg:.0f}W" if work_power_avg else "")
        )

        # Bullet 2: Recovery segments (if exist)
        if recovery_splits and recovery_pace_avg and recovery_hr_avg:
            recovery_pace_min = int(recovery_pace_avg // 60)
            recovery_pace_sec = int(recovery_pace_avg % 60)
            recovery_pace_str = f"{recovery_pace_min}:{recovery_pace_sec:02d}/km"
            bullets.append(
                f"- Recovery区間{len(recovery_splits)}本: 平均ペース{recovery_pace_str}、"
                f"平均心拍{recovery_hr_avg:.0f}bpm（十分な回復）"
            )

        # Bullet 3: Work consistency
        if len(work_splits) > 1:
            work_pace_std = (
                sum(
                    (s["pace_seconds_per_km"] - work_pace_avg) ** 2 for s in work_splits
                )
                / len(work_splits)
            ) ** 0.5
            pace_cv = (work_pace_std / work_pace_avg) * 100  # Coefficient of variation

            if pace_cv < 2.0:
                consistency = "非常に安定"
            elif pace_cv < 4.0:
                consistency = "安定"
            else:
                consistency = "やや不安定"

            bullets.append(f"- Workペース変動係数: {pace_cv:.1f}% ({consistency})")

        # Bullet 4: Transition quality (if recovery exists)
        if recovery_splits and recovery_hr_avg:
            hr_drop = work_hr_avg - recovery_hr_avg
            if hr_drop > 30:
                transition = "優秀な心拍リカバリー"
            elif hr_drop > 20:
                transition = "良好な心拍リカバリー"
            else:
                transition = "心拍リカバリーやや不十分"

            bullets.append(f"- Work→Recovery心拍低下: {hr_drop:.0f}bpm ({transition})")

        return "\n".join(bullets)

    def generate_hr_zone_pie_data(self, activity_id: int) -> str | None:
        """
        Generate Mermaid pie chart data for heart rate zones.

        Args:
            activity_id: Activity ID

        Returns:
            Mermaid pie chart data string or None if no data available
        """
        try:
            result = self.db_reader.execute_read_query(
                """
                SELECT
                    zone_number,
                    zone_percentage
                FROM heart_rate_zones
                WHERE activity_id = ?
                AND zone_percentage > 0
                ORDER BY zone_number
                """,
                (activity_id,),
            )

            if not result:
                return None

            # Japanese zone name mapping
            zone_names = {
                1: "Zone 1 (回復)",
                2: "Zone 2 (有酸素)",
                3: "Zone 3 (テンポ)",
                4: "Zone 4 (閾値)",
                5: "Zone 5 (最大)",
            }

            # Format as Mermaid pie chart data
            pie_lines = []
            for zone_number, percentage in result:
                zone_label = zone_names.get(zone_number, f"Zone {zone_number}")
                pie_lines.append(f'    "{zone_label}" : {percentage:.2f}')

            if not pie_lines:
                return None

            return "\n".join(pie_lines)

        except Exception as e:
            logger.warning(f"Failed to generate HR zone pie data: {e}")
            return None
