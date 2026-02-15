"""Physiological calculation components extracted from ReportGeneratorWorker."""

import logging
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.formatting import format_pace

logger = logging.getLogger(__name__)


class PhysiologicalCalculator:
    """Calculates physiological indicators and form efficiency metrics."""

    def __init__(self, db_reader: GarminDBReader) -> None:
        self.db_reader = db_reader

    def calculate_physiological_indicators(
        self,
        training_type_category: str,
        vo2_max_data: dict[str, Any] | None,
        lactate_threshold_data: dict[str, Any] | None,
        run_metrics: dict[str, Any],
        hr_zone_times: list[tuple[int, float]] | None = None,
    ) -> dict[str, Any]:
        """Calculate physiological indicators for tempo/threshold/interval workouts.

        Args:
            training_type_category: Training type category from get_training_type_category
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database
            run_metrics: Run/main phase metrics
            hr_zone_times: List of (zone_number, time_in_zone_seconds) tuples

        Returns:
            Dictionary with physiological indicators (empty dict if low_moderate or missing data)
        """
        # Only calculate for tempo_threshold and interval_sprint
        if training_type_category == "low_moderate":
            return {}

        # Check that at least run_metrics is available
        if not run_metrics:
            return {}

        result: dict[str, Any] = {}

        # Extract values with None checks
        vo2_max_value = vo2_max_data.get("precise_value") if vo2_max_data else None
        threshold_speed = (
            lactate_threshold_data.get("speed_mps") if lactate_threshold_data else None
        )
        ftp = (
            lactate_threshold_data.get("functional_threshold_power")
            if lactate_threshold_data
            else None
        )
        target_pace = run_metrics.get("avg_pace_seconds_per_km")
        work_avg_power = run_metrics.get("avg_power", 0)

        # Calculate VO2 Max utilization
        if vo2_max_value and target_pace:
            # Empirical formula: vVO2max (km/h) ~ VO2max / 3.5
            vo2_max_speed_kmh = vo2_max_value / 3.5
            vo2_max_pace_seconds_per_km = 3600 / vo2_max_speed_kmh

            # Utilization = VO2max pace / current pace * 100
            vo2_max_utilization = (vo2_max_pace_seconds_per_km / target_pace) * 100
            result["vo2_max_utilization"] = round(vo2_max_utilization, 1)

            # Evaluation text
            if vo2_max_utilization >= 90:
                result["vo2_max_utilization_eval"] = "非常に高強度"
                result["vo2_max_expected_effect"] = (
                    "VO2 max（最大酸素摂取量）の大幅向上が期待できます。"
                    "心肺機能が強化され、高強度での持久力が向上します。"
                )
            elif vo2_max_utilization >= 80:
                result["vo2_max_utilization_eval"] = "高強度（閾値〜VO2max）"
                result["vo2_max_expected_effect"] = (
                    "乳酸閾値とVO2 maxの両方が向上します。"
                    "閾値ペースでの持久力と高強度での走力が同時に強化されます。"
                )
            elif vo2_max_utilization >= 70:
                result["vo2_max_utilization_eval"] = "中高強度（テンポ〜閾値）"
                result["vo2_max_expected_effect"] = (
                    "主に乳酸閾値の向上が期待できます。"
                    "閾値ペースでの持久力が強化され、レースペースの維持能力が向上します。"
                )
            else:
                result["vo2_max_utilization_eval"] = "中強度"
                result["vo2_max_expected_effect"] = (
                    "有酸素基礎の強化が主な効果です。"
                    "持久力の土台が構築され、長距離を走る能力が向上します。"
                )

        # Format threshold pace and comparison
        if threshold_speed and target_pace:
            threshold_pace_seconds_per_km = 1000 / threshold_speed
            result["threshold_pace_formatted"] = format_pace(
                threshold_pace_seconds_per_km
            )

            # Comparison
            pace_diff = target_pace - threshold_pace_seconds_per_km
            if abs(pace_diff) < 5:
                result["threshold_pace_comparison"] = "閾値ペースと同等"
            elif pace_diff > 0:
                result["threshold_pace_comparison"] = (
                    f"閾値より{abs(pace_diff):.0f}秒/km遅い"
                )
            else:
                result["threshold_pace_comparison"] = (
                    f"閾値より{abs(pace_diff):.0f}秒/km速い"
                )

        # Calculate FTP percentage and work power
        if ftp and ftp > 0 and work_avg_power:
            ftp_pct = round((work_avg_power / ftp) * 100, 1)
            result["ftp_percentage"] = ftp_pct
            result["work_avg_power"] = round(work_avg_power, 0)

            # Determine power zone name based on FTP percentage
            if ftp_pct < 55:
                result["power_zone_name"] = "Zone 1 (リカバリー)"
            elif ftp_pct < 75:
                result["power_zone_name"] = "Zone 2 (持久力)"
            elif ftp_pct < 90:
                result["power_zone_name"] = "Zone 3 (テンポ)"
            elif ftp_pct < 105:
                result["power_zone_name"] = "Zone 4 (閾値)"
            elif ftp_pct < 120:
                result["power_zone_name"] = "Zone 5 (VO2 Max)"
            elif ftp_pct < 150:
                result["power_zone_name"] = "Zone 6 (無酸素)"
            else:
                result["power_zone_name"] = "Zone 7 (神経筋)"

        # Calculate threshold expected effect based on heart rate
        if lactate_threshold_data and run_metrics:
            threshold_hr = lactate_threshold_data.get("heart_rate")
            work_avg_hr = run_metrics.get("avg_hr")

            if threshold_hr and work_avg_hr:
                hr_diff = work_avg_hr - threshold_hr

                if hr_diff > 5:
                    result["threshold_expected_effect"] = (
                        "閾値心拍を超える強度により、VO2 maxの向上効果が高まります。"
                        "最大酸素摂取量が発達し、高強度での走力が強化されます。"
                    )
                elif hr_diff >= -5:
                    result["threshold_expected_effect"] = (
                        "乳酸閾値の向上に最適な強度です。"
                        "閾値ペースでの持久力が向上し、レースペースの維持能力が強化されます。"
                    )
                else:
                    result["threshold_expected_effect"] = (
                        "閾値ペース感覚の習得と有酸素持久力の向上が期待できます。"
                        "閾値走の基礎が構築され、徐々に強度を上げる準備が整います。"
                    )

        # Calculate Zone 4 ratio (for threshold training)
        if training_type_category == "tempo_threshold" and hr_zone_times:
            # hr_zone_times is a list of (zone_number, time_in_zone_seconds) tuples
            zone_dict = dict(hr_zone_times)

            total_time = sum(zone_dict.values())
            zone_4_time = zone_dict.get(4, 0)

            if total_time > 0:
                zone_4_ratio = (zone_4_time / total_time) * 100
                result["zone_4_ratio"] = round(zone_4_ratio, 1)

        return result

    def calculate_run_phase_power_stride(
        self, activity_id: int
    ) -> dict[str, float | None]:
        """Calculate average power and stride length for run phase.

        Args:
            activity_id: Activity ID

        Returns:
            Dictionary with avg_power and avg_stride (None if no data)
        """
        try:
            results = self.db_reader.execute_read_query(
                """
                SELECT
                    AVG(power) as avg_power,
                    AVG(stride_length) as avg_stride
                FROM splits
                WHERE activity_id = ?
                  AND role_phase = 'run'
                  AND power IS NOT NULL
                  AND stride_length IS NOT NULL
                """,
                (activity_id,),
            )
            result = results[0] if results else None

            if result and result[0] is not None and result[1] is not None:
                return {
                    "avg_power": round(result[0], 1),
                    "avg_stride": round(result[1], 2),
                }
            return {"avg_power": None, "avg_stride": None}

        except Exception as e:
            logger.error(
                f"Error calculating run phase power/stride for activity {activity_id}: {e}"
            )
            return {"avg_power": None, "avg_stride": None}

    def calculate_power_stride_baselines(
        self,
        activity_id: int,
        similar_workouts: dict[str, Any] | None = None,
        training_type: str | None = None,
    ) -> dict[str, float | None]:
        """Calculate baseline power and stride from similar workouts.

        Args:
            activity_id: Current activity ID
            similar_workouts: Similar workouts data from WorkoutComparator
            training_type: Training type for role_phase filtering

        Returns:
            Dictionary with baseline_power and baseline_stride (None if insufficient data)
        """
        try:
            # Use similar workouts from WorkoutComparator if available
            if similar_workouts and "similar_activities" in similar_workouts:
                similar_ids = [
                    sw["activity_id"]
                    for sw in similar_workouts["similar_activities"][:5]
                ]
            else:
                # Fallback: query by distance/pace (legacy behavior)
                current_results = self.db_reader.execute_read_query(
                    """
                    SELECT total_distance_km, avg_pace_seconds_per_km
                    FROM activities
                    WHERE activity_id = ?
                    """,
                    (activity_id,),
                )
                current_activity = current_results[0] if current_results else None

                if not current_activity:
                    return {"baseline_power": None, "baseline_stride": None}

                target_distance, target_pace = current_activity
                distance_min = target_distance * 0.9
                distance_max = target_distance * 1.1
                pace_min = target_pace * 0.9
                pace_max = target_pace * 1.1

                similar_activities = self.db_reader.execute_read_query(
                    """
                    SELECT activity_id
                    FROM activities
                    WHERE activity_id != ?
                      AND total_distance_km BETWEEN ? AND ?
                      AND avg_pace_seconds_per_km BETWEEN ? AND ?
                    ORDER BY
                        ABS(total_distance_km - ?) +
                        ABS(avg_pace_seconds_per_km - ?)
                    LIMIT 5
                    """,
                    (
                        activity_id,
                        distance_min,
                        distance_max,
                        pace_min,
                        pace_max,
                        target_distance,
                        target_pace,
                    ),
                )

                similar_ids = [row[0] for row in similar_activities]

            if len(similar_ids) < 1:
                return {"baseline_power": None, "baseline_stride": None}

            power_values: list[float] = []
            stride_values: list[float] = []

            # Determine role_phase filter based on training type
            structured_types = {
                "tempo",
                "lactate_threshold",
                "vo2max",
                "anaerobic_capacity",
                "speed",
                "interval_training",
            }
            use_run_phase_only = training_type in structured_types

            for sim_activity_id in similar_ids:
                # Query power and stride for each similar workout
                if use_run_phase_only:
                    # For structured workouts, only use run phase
                    results = self.db_reader.execute_read_query(
                        """
                        SELECT
                            AVG(power) as avg_power,
                            AVG(stride_length) as avg_stride
                        FROM splits
                        WHERE activity_id = ?
                          AND role_phase = 'run'
                          AND power IS NOT NULL
                          AND stride_length IS NOT NULL
                        """,
                        (sim_activity_id,),
                    )
                else:
                    # For base/recovery runs, use all splits
                    results = self.db_reader.execute_read_query(
                        """
                        SELECT
                            AVG(power) as avg_power,
                            AVG(stride_length) as avg_stride
                        FROM splits
                        WHERE activity_id = ?
                          AND power IS NOT NULL
                          AND stride_length IS NOT NULL
                        """,
                        (sim_activity_id,),
                    )
                result = results[0] if results else None

                if result and result[0] is not None:
                    power_values.append(result[0])
                if result and result[1] is not None:
                    stride_values.append(result[1])

            # Require at least 1 similar workout with data
            baseline_power = (
                round(sum(power_values) / len(power_values), 1)
                if len(power_values) >= 1
                else None
            )
            baseline_stride = (
                round(sum(stride_values) / len(stride_values), 2)
                if len(stride_values) >= 1
                else None
            )

            return {
                "baseline_power": baseline_power,
                "baseline_stride": baseline_stride,
            }

        except Exception as e:
            logger.error(f"Error calculating power/stride baselines: {e}")
            return {"baseline_power": None, "baseline_stride": None}

    def calculate_pace_corrected_form_efficiency(
        self,
        avg_pace_seconds_per_km: float,
        form_eff: dict[str, Any],
        run_power: float | None = None,
        run_stride: float | None = None,
        baseline_power: float | None = None,
        baseline_stride: float | None = None,
    ) -> dict[str, Any]:
        """Calculate pace-corrected form efficiency scores.

        Formulas from planning.md Appendix C:
        - GCT baseline: 230 + (pace - 240) * 0.22 ms
        - VO baseline: 6.8 + (pace - 240) * 0.004 cm
        - VR: No correction, absolute threshold 8.0-9.5%
        - Power: Baseline from similar workout average
        - Stride: Baseline from similar workout average

        Args:
            avg_pace_seconds_per_km: Average pace in seconds per km
            form_eff: Form efficiency dictionary with gct_average, vo_average, vr_average
            run_power: Average power during run phase (W)
            run_stride: Average stride length during run phase (cm)
            baseline_power: Baseline power from similar workouts (W)
            baseline_stride: Baseline stride from similar workouts (cm)

        Returns:
            Dictionary with pace-corrected form efficiency data
        """
        # Baseline calculations
        baseline_gct = 230 + (avg_pace_seconds_per_km - 240) * 0.22
        baseline_vo = 6.8 + (avg_pace_seconds_per_km - 240) * 0.004

        # GCT efficiency
        gct_actual = form_eff.get("gct_average", 0)
        gct_score = (
            ((gct_actual - baseline_gct) / baseline_gct) * 100
            if baseline_gct > 0
            else 0
        )
        gct_label = (
            "優秀" if gct_score < -5 else ("良好" if abs(gct_score) <= 5 else "要改善")
        )
        gct_rating = (
            5.0
            if gct_score < -5
            else (4.5 if gct_score < -2 else (4.0 if abs(gct_score) <= 5 else 3.0))
        )

        # VO efficiency
        vo_actual = form_eff.get("vo_average", 0)
        vo_score = (
            ((vo_actual - baseline_vo) / baseline_vo) * 100 if baseline_vo > 0 else 0
        )
        vo_label = (
            "優秀" if vo_score < -5 else ("良好" if abs(vo_score) <= 5 else "要改善")
        )
        vo_rating = (
            5.0
            if vo_score < -5
            else (4.5 if vo_score < -2 else (4.0 if abs(vo_score) <= 5 else 3.0))
        )

        # VR (no pace correction)
        vr_actual = form_eff.get("vr_average", 0)
        vr_label = "理想範囲内" if 8.0 <= vr_actual <= 9.5 else "要改善"
        vr_rating = 5.0 if 8.0 <= vr_actual <= 9.5 else 3.5

        result: dict[str, Any] = {
            "avg_pace_seconds": int(avg_pace_seconds_per_km),
            "gct": {
                "actual": round(gct_actual, 1),
                "baseline": round(baseline_gct, 1),
                "score": round(gct_score, 1),
                "label": gct_label,
                "rating_stars": "★" * int(gct_rating) + "☆" * (5 - int(gct_rating)),
                "rating_score": gct_rating,
            },
            "vo": {
                "actual": round(vo_actual, 2),
                "baseline": round(baseline_vo, 2),
                "score": round(vo_score, 1),
                "label": vo_label,
                "rating_stars": "★" * int(vo_rating) + "☆" * (5 - int(vo_rating)),
                "rating_score": vo_rating,
            },
            "vr": {
                "actual": round(vr_actual, 2),
                "label": vr_label,
                "rating_stars": "★" * int(vr_rating) + "☆" * (5 - int(vr_rating)),
                "rating_score": vr_rating,
            },
        }

        # Power efficiency (if data available)
        if run_power is not None and baseline_power is not None and baseline_power > 0:
            power_score = ((run_power - baseline_power) / baseline_power) * 100
            if abs(power_score) <= 3:
                power_label = "安定"
                power_rating = 4.5
            elif power_score > 3:
                power_label = "上昇"
                power_rating = 4.0
            else:
                power_label = "効率向上"
                power_rating = 5.0

            result["power"] = {
                "actual": round(run_power, 1),
                "baseline": round(baseline_power, 1),
                "score": round(power_score, 1),
                "label": power_label,
                "rating_stars": "★" * int(power_rating) + "☆" * (5 - int(power_rating)),
                "rating_score": power_rating,
            }

        # Stride efficiency (if data available)
        if (
            run_stride is not None
            and baseline_stride is not None
            and baseline_stride > 0
        ):
            stride_score = ((run_stride - baseline_stride) / baseline_stride) * 100
            if 0 <= stride_score <= 5:
                stride_label = "拡大"
                stride_rating = 4.5
            elif abs(stride_score) <= 2:
                stride_label = "安定"
                stride_rating = 4.5
            elif stride_score < -2:
                stride_label = "短縮"
                stride_rating = 4.0
            else:
                stride_label = "大幅拡大"
                stride_rating = 4.0

            result["stride"] = {
                "actual": round(run_stride / 100, 2),  # Convert cm to m
                "baseline": round(baseline_stride / 100, 2),  # Convert cm to m
                "score": round(stride_score, 1),
                "label": stride_label,
                "rating_stars": "★" * int(stride_rating)
                + "☆" * (5 - int(stride_rating)),
                "rating_score": stride_rating,
            }

        return result

    def build_form_efficiency_table(
        self, pace_corrected_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build form efficiency table structure for template rendering.

        Transforms pace-corrected form efficiency data into table format
        compatible with BALANCED template requirements.

        Args:
            pace_corrected_data: Output from calculate_pace_corrected_form_efficiency()

        Returns:
            Dictionary with overall_form_score and form_efficiency_table array
        """
        table: list[dict[str, str]] = []
        rating_scores: list[float] = []

        # GCT row
        gct = pace_corrected_data["gct"]
        table.append(
            {
                "metric_name": "接地時間",
                "actual_value": f"{gct['actual']}ms",
                "baseline_value": f"{gct['baseline']}ms",
                "adjusted_score": f"**{gct['score']:+.1f}%** {gct['label']}",
                "rating": f"{gct['rating_stars']} {gct['rating_score']}",
            }
        )
        rating_scores.append(gct["rating_score"])

        # VO row
        vo = pace_corrected_data["vo"]
        table.append(
            {
                "metric_name": "垂直振幅",
                "actual_value": f"{vo['actual']:.2f}cm",
                "baseline_value": f"{vo['baseline']:.2f}cm",
                "adjusted_score": f"**{vo['score']:+.1f}%** {vo['label']}",
                "rating": f"{vo['rating_stars']} {vo['rating_score']}",
            }
        )
        rating_scores.append(vo["rating_score"])

        # VR row (no baseline, uses range)
        vr = pace_corrected_data["vr"]
        table.append(
            {
                "metric_name": "垂直比率",
                "actual_value": f"{vr['actual']:.2f}%",
                "baseline_value": "8.0-9.5%",
                "adjusted_score": vr["label"],
                "rating": f"{vr['rating_stars']} {vr['rating_score']}",
            }
        )
        rating_scores.append(vr["rating_score"])

        # Power row (if available)
        if "power" in pace_corrected_data:
            power = pace_corrected_data["power"]
            table.append(
                {
                    "metric_name": "パワー",
                    "actual_value": f"{int(power['actual'])}W",
                    "baseline_value": f"{int(power['baseline'])}W（類似平均）",
                    "adjusted_score": f"**{power['score']:+.1f}%** {power['label']}",
                    "rating": f"{power['rating_stars']} {power['rating_score']}",
                }
            )
            rating_scores.append(power["rating_score"])

        # Stride row (if available)
        if "stride" in pace_corrected_data:
            stride = pace_corrected_data["stride"]
            table.append(
                {
                    "metric_name": "ストライド長",
                    "actual_value": f"{stride['actual']:.2f}m",
                    "baseline_value": f"{stride['baseline']:.2f}m（類似平均）",
                    "adjusted_score": f"**{stride['score']:+.1f}%** {stride['label']}",
                    "rating": f"{stride['rating_stars']} {stride['rating_score']}",
                }
            )
            rating_scores.append(stride["rating_score"])

        # Calculate overall form score (average of all available ratings)
        avg_rating = sum(rating_scores) / len(rating_scores)
        rating_stars = "★" * int(avg_rating) + "☆" * (5 - int(avg_rating))
        overall_form_score = f"{rating_stars} {avg_rating:.1f}/5.0"

        return {
            "overall_form_score": overall_form_score,
            "form_efficiency_table": table,
        }
