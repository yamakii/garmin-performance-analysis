"""Workout comparison components extracted from ReportGeneratorWorker."""

import logging
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.formatting import format_pace

logger = logging.getLogger(__name__)


class WorkoutComparator:
    """Compares current workout with similar past workouts."""

    def __init__(self, db_reader: GarminDBReader) -> None:
        self.db_reader = db_reader

    def get_comparison_pace(
        self, performance_data: dict[str, Any]
    ) -> tuple[float, str]:
        """
        Determine which pace to use for similarity comparison.

        Args:
            performance_data: Performance data dict with training_type, run_metrics, basic_metrics

        Returns:
            tuple: (pace_seconds_per_km, pace_source)
            - pace_source: "main_set" | "overall"
        """
        training_type = performance_data.get("training_type", "unknown")
        structured_types = {
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        }

        # Use main set pace for structured workouts (if available)
        if training_type in structured_types:
            run_metrics = performance_data.get("run_metrics")
            if run_metrics and run_metrics.get("avg_pace_seconds_per_km"):
                return (run_metrics["avg_pace_seconds_per_km"], "main_set")

        # Fallback: use overall average pace
        return (performance_data["basic_metrics"]["avg_pace_seconds_per_km"], "overall")

    def get_evaluation_target_text(self, training_type_category: str) -> str:
        """
        Get evaluation target description text based on training type.

        Args:
            training_type_category: "low_moderate" | "tempo_threshold" | "interval_sprint"

        Returns:
            Japanese description of evaluation target segments
        """
        if training_type_category == "interval_sprint":
            return "Workセグメント5本のみ（インターバル走は高強度区間のパフォーマンスを重視）"
        elif training_type_category == "tempo_threshold":
            return "メイン区間（Split 3-6）のみ（閾値走は高強度区間のパフォーマンスを重視）"
        else:
            return ""

    def load_similar_workouts(
        self, activity_id: int, current_metrics: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Load similar workouts comparison using MCP tool.

        Returns None if insufficient data or error occurs.

        Args:
            activity_id: Activity ID to find similar workouts for
            current_metrics: Dictionary with 'avg_pace', 'avg_hr', and 'pace_source' keys

        Returns:
            Dictionary with comparison data or None
        """
        try:
            # Import WorkoutComparator from correct location
            from garmin_mcp.rag.queries.comparisons import (
                WorkoutComparator as RagComparator,
            )

            comparator = RagComparator()

            # Pass target_pace_override for structured workouts (main-set pace comparison)
            target_pace_override = None
            if current_metrics.get("pace_source") == "main_set":
                target_pace_override = current_metrics["avg_pace"]

            result = comparator.find_similar_workouts(
                activity_id=activity_id,
                distance_tolerance=0.20,
                pace_tolerance=0.20,
                terrain_match=True,
                limit=10,
                target_pace_override=target_pace_override,
            )

            # Extract workouts list from result (correct key name)
            similar = result.get("similar_activities", [])

            if not similar or len(similar) < 1:
                logger.warning(f"No similar workouts found for activity {activity_id}")
                return None

            # Calculate average differences from top 3
            top_3 = similar[:3]

            # For main_set comparison, recalculate pace_diff from actual main set paces
            if current_metrics.get("pace_source") == "main_set":

                base_pace = current_metrics[
                    "avg_pace"
                ]  # Current activity's main set pace

                for workout in top_3:
                    # Query similar activity's main set pace
                    query_results = self.db_reader.execute_read_query(
                        """
                        SELECT AVG(pace_seconds_per_km) as main_pace
                        FROM splits
                        WHERE activity_id = ?
                          AND intensity_type IN ('ACTIVE', 'INTERVAL')
                    """,
                        (workout["activity_id"],),
                    )
                    query_result = query_results[0] if query_results else None

                    if query_result and query_result[0]:
                        similar_main_pace = query_result[0]
                        # Recalculate pace_diff relative to current main set pace
                        workout["pace_diff"] = base_pace - similar_main_pace
                    else:
                        # Fallback: if no main set data, use overall pace diff
                        logger.warning(
                            f"No main set data for activity {workout['activity_id']}, "
                            f"using overall pace diff"
                        )

            # Use target_pace_override for main-set comparison, otherwise use overall avg_pace
            base_pace = (
                target_pace_override
                if target_pace_override
                else current_metrics["avg_pace"]
            )

            # Calculate average of similar workouts by computing each workout's actual value first
            similar_paces = [base_pace + w["pace_diff"] for w in top_3]
            avg_similar_pace = sum(similar_paces) / len(similar_paces)

            similar_hrs = [current_metrics["avg_hr"] + w["hr_diff"] for w in top_3]
            avg_similar_hr = sum(similar_hrs) / len(similar_hrs)

            # Calculate average differences for display
            avg_pace_diff = sum([w["pace_diff"] for w in top_3]) / len(top_3)
            avg_hr_diff = sum([w["hr_diff"] for w in top_3]) / len(top_3)

            pace_diff = avg_pace_diff
            hr_diff = avg_hr_diff

            # Determine which pace to use for comparison
            pace_source = current_metrics.get("pace_source", "overall")

            # For main_set comparison, filter by intensity_type
            if pace_source == "main_set":
                intensity_filter = "AND intensity_type IN ('ACTIVE', 'INTERVAL')"
            else:
                intensity_filter = ""

            # Get additional metrics from splits table

            # Get current activity metrics (filtered by intensity_type if main_set)
            current_additional_results = self.db_reader.execute_read_query(
                f"""
                SELECT
                    AVG(power) as avg_power,
                    AVG(stride_length) as avg_stride_cm,
                    AVG(ground_contact_time) as avg_gct,
                    AVG(vertical_oscillation) as avg_vo
                FROM splits
                WHERE activity_id = ? {intensity_filter}
                """,
                (activity_id,),
            )
            current_additional = (
                current_additional_results[0] if current_additional_results else None
            )

            # Get similar activities metrics (same filtering)
            similar_ids = [w["activity_id"] for w in top_3]
            similar_additional_results = self.db_reader.execute_read_query(
                f"""
                SELECT
                    AVG(power) as avg_power,
                    AVG(stride_length) as avg_stride_cm,
                    AVG(ground_contact_time) as avg_gct,
                    AVG(vertical_oscillation) as avg_vo
                FROM splits
                WHERE activity_id IN ({",".join("?" * len(similar_ids))}) {intensity_filter}
                """,
                tuple(similar_ids),
            )
            similar_additional = (
                similar_additional_results[0] if similar_additional_results else None
            )

            # Format comparison table
            comparisons: list[dict[str, str]] = [
                {
                    "metric": "平均ペース",
                    "current": format_pace(base_pace),
                    "average": format_pace(avg_similar_pace),
                    "change": (
                        f"+{abs(int(pace_diff))}秒速い"
                        if pace_diff > 0
                        else f"-{abs(int(pace_diff))}秒遅い"
                    ),
                    "trend": (
                        "↗️ 改善"
                        if pace_diff > 0
                        else ("↘️ 悪化" if pace_diff < -5 else "➡️ 同等")
                    ),
                },
                {
                    "metric": "平均心拍",
                    "current": f"{int(current_metrics['avg_hr'])} bpm",
                    "average": f"{int(avg_similar_hr)} bpm",
                    "change": (
                        f"+{int(hr_diff)} bpm" if hr_diff > 0 else f"{int(hr_diff)} bpm"
                    ),
                    "trend": (
                        "➡️ 同等"
                        if abs(hr_diff) < 5
                        else ("✅ 低い" if hr_diff > 0 else "⚠️ 高い")
                    ),
                },
            ]

            # Add additional metrics if available
            if current_additional:
                self._add_additional_comparisons(
                    comparisons, current_additional, similar_additional
                )

            # Add training-type-specific metrics
            try:
                hr_data = self.db_reader.get_hr_efficiency_analysis(activity_id)
                training_type = hr_data.get("training_type") if hr_data else None

                # Pace variability coefficient - now for ALL training types
                cv_results = self.db_reader.execute_read_query(
                    f"""
                    SELECT STDDEV(pace_seconds_per_km) / AVG(pace_seconds_per_km) as pace_cv
                    FROM splits
                    WHERE activity_id = ? {intensity_filter}
                    """,
                    (activity_id,),
                )
                current_pace_cv = cv_results[0][0] if cv_results else None

                # Calculate average pace CV for similar activities
                similar_pace_cvs = []
                for sim_id in similar_ids:
                    sim_cv_results = self.db_reader.execute_read_query(
                        f"""
                        SELECT STDDEV(pace_seconds_per_km) / AVG(pace_seconds_per_km) as pace_cv
                        FROM splits
                        WHERE activity_id = ? {intensity_filter}
                        """,
                        (sim_id,),
                    )
                    sim_cv = sim_cv_results[0][0] if sim_cv_results else None

                    if sim_cv:
                        similar_pace_cvs.append(sim_cv)

                if current_pace_cv:
                    if similar_pace_cvs:
                        avg_similar_cv = sum(similar_pace_cvs) / len(similar_pace_cvs)
                        pace_cv_diff = current_pace_cv - avg_similar_cv
                        comparisons.append(
                            {
                                "metric": "ペース変動係数",
                                "current": f"{current_pace_cv:.3f}",
                                "average": f"{avg_similar_cv:.3f}",
                                "change": f"{pace_cv_diff:+.3f}",
                                "trend": (
                                    "↗️ 安定性向上"
                                    if pace_cv_diff < 0
                                    else (
                                        "➡️ 維持"
                                        if abs(pace_cv_diff) < 0.01
                                        else "↘️ ばらつき増"
                                    )
                                ),
                            }
                        )
                    else:
                        comparisons.append(
                            {
                                "metric": "ペース変動係数",
                                "current": f"{current_pace_cv:.3f}",
                                "average": "N/A",
                                "change": "N/A",
                                "trend": "N/A",
                            }
                        )

                # Recovery rate for Interval activities only
                if training_type in [
                    "interval_training",
                    "high_intensity",
                    "vo2max",
                    "anaerobic_capacity",
                ]:
                    self._add_recovery_rate_comparison(
                        comparisons, activity_id, similar_ids
                    )

            except Exception as e:
                logger.warning(
                    f"Could not calculate training-type-specific metrics: {e}"
                )

            # Get training type and terrain BEFORE closing connection
            hr_data_for_conditions = self.db_reader.get_hr_efficiency_analysis(
                activity_id
            )
            training_type_raw = (
                hr_data_for_conditions.get("training_type")
                if hr_data_for_conditions
                else None
            )

            # Get elevation gain for terrain description from splits
            elevation_results = self.db_reader.execute_read_query(
                """
                SELECT SUM(elevation_gain) as total_gain
                FROM splits
                WHERE activity_id = ?
                """,
                (activity_id,),
            )
            elevation_data = elevation_results[0] if elevation_results else None
            elevation_gain = (
                elevation_data[0] if elevation_data and elevation_data[0] else 0
            )

            # Generate insight with efficiency calculation if applicable
            insight = f"過去の類似ワークアウト{len(top_3)}回と比較して分析しました。"

            # Add detailed efficiency insight if pace improved and power decreased
            if (
                current_additional
                and similar_additional
                and current_additional[0]
                and similar_additional[0]
            ):
                power_diff = current_additional[0] - similar_additional[0]

                if pace_diff < 0 and power_diff < 0:
                    efficiency_improvement = (
                        abs(power_diff / similar_additional[0]) * 100
                    )
                    pace_improvement = abs(int(pace_diff))
                    power_reduction = abs(int(power_diff))

                    insight = f"ペース{pace_improvement}秒速いのにパワー{power_reduction}W低下＝**効率が{efficiency_improvement:.1f}%向上** ✅"
                elif len([c for c in comparisons if "改善" in c.get("trend", "")]) >= 3:
                    insight = "複数指標で改善が見られます"

            # Format conditions description with training type and terrain
            target_distance = result.get("target_activity", {}).get("distance_km", 0)

            # Distance description
            distance_rounded = round(target_distance)
            distance_desc = f"{distance_rounded}km前後"

            # Pace description with concrete range from similar activities
            if similar and len(similar) >= 3:
                target_pace_val = result.get("target_activity", {}).get(
                    "avg_pace", current_metrics["avg_pace"]
                )
                pace_values = [target_pace_val - sw["pace_diff"] for sw in similar[:3]]
                min_pace = min(pace_values)
                max_pace = max(pace_values)

                min_pace_str = format_pace(min_pace)
                max_pace_str = format_pace(max_pace)

                training_type_map = {
                    "low_intensity": "イージーペース",
                    "moderate_intensity": "ジョグペース",
                    "lactate_threshold": "閾値ペース",
                    "tempo": "テンポペース",
                    "interval_training": "インターバルペース",
                    "high_intensity": "高強度ペース",
                    "vo2max": "VO2 Maxペース",
                    "anaerobic_capacity": "無酸素ペース",
                }
                training_type_label = training_type_map.get(training_type_raw or "")

                if training_type_label:
                    pace_desc = training_type_label
                else:
                    min_pace_base = min_pace_str.replace("/km", "")
                    max_pace_base = max_pace_str.replace("/km", "")
                    pace_desc = f"ペース{min_pace_base}-{max_pace_base}/km"
            else:
                pace_desc = "ペース類似"

            # Terrain description based on elevation gain
            if elevation_gain < 100:
                terrain_desc = "平坦コース"
            elif elevation_gain < 300:
                terrain_desc = "起伏コース"
            elif elevation_gain < 600:
                terrain_desc = "丘陵コース"
            else:
                terrain_desc = "山岳コース"

            conditions_text = f"距離{distance_desc}、{pace_desc}、{terrain_desc}"

            return {
                "conditions": conditions_text,
                "count": len(top_3),
                "comparisons": comparisons,
                "insight": insight,
                "pace_source": current_metrics.get("pace_source", "overall"),
                "similar_activities": similar,
            }

        except Exception as e:
            logger.warning(f"Could not load similar workouts: {e}")
            return None

    def generate_comparison_insights(
        self, activity_id: int, performance_data: dict[str, Any]
    ) -> list[str]:
        """
        Generate insights by comparing with previous similar workout.

        Args:
            activity_id: Current activity ID
            performance_data: Current activity performance data

        Returns:
            List of insight strings to add to key_strengths
        """
        insights: list[str] = []

        try:
            # Get current activity metrics
            current_results = self.db_reader.execute_read_query(
                """
                SELECT
                    a.activity_date,
                    a.avg_heart_rate,
                    a.avg_pace_seconds_per_km,
                    a.total_distance_km,
                    f.gct_average
                FROM activities a
                LEFT JOIN form_efficiency f ON a.activity_id = f.activity_id
                WHERE a.activity_id = ?
                """,
                (activity_id,),
            )
            current = current_results[0] if current_results else None

            if not current:
                return insights

            current_date, current_hr, current_pace, current_dist, current_gct = current

            # Find most recent similar workout (within +/-10% pace and distance)
            previous_results = self.db_reader.execute_read_query(
                """
                SELECT
                    a.activity_id,
                    a.activity_date,
                    a.avg_heart_rate,
                    a.avg_pace_seconds_per_km,
                    f.gct_average
                FROM activities a
                LEFT JOIN form_efficiency f ON a.activity_id = f.activity_id
                WHERE a.activity_id != ?
                    AND a.activity_date < ?
                    AND a.avg_pace_seconds_per_km BETWEEN ? * 0.9 AND ? * 1.1
                    AND a.total_distance_km BETWEEN ? * 0.9 AND ? * 1.1
                ORDER BY a.activity_date DESC
                LIMIT 1
                """,
                (
                    activity_id,
                    current_date,
                    current_pace,
                    current_pace,
                    current_dist,
                    current_dist,
                ),
            )
            previous = previous_results[0] if previous_results else None

            if not previous:
                return insights

            prev_id, prev_date, prev_hr, prev_pace, prev_gct = previous

            # Compare heart rate (lower is better at same pace)
            hr_diff: float = 0
            if current_hr and prev_hr:
                hr_diff = current_hr - prev_hr
                if hr_diff <= -1:
                    insights.append(
                        f"**心拍効率向上**: 同ペースで前回比{hr_diff}bpm（有酸素能力向上）✅"
                    )

            # Compare GCT (lower is better)
            if current_gct and prev_gct:
                gct_diff = current_gct - prev_gct
                gct_pct = (gct_diff / prev_gct) * 100 if prev_gct > 0 else 0
                if gct_diff <= -1:
                    insights.append(
                        f"**GCT改善**: 前回比{gct_diff:.1f}ms（効率{abs(gct_pct):.1f}%向上）✅"
                    )

            # Compare pace (faster is better at same HR)
            if current_pace and prev_pace:
                pace_diff = current_pace - prev_pace
                if pace_diff < -2 and abs(hr_diff) <= 2:
                    insights.append(
                        f"**ペース向上**: 前回比{abs(pace_diff):.1f}秒/km速く、心拍効率も改善✅"
                    )

            # Add general comparison note
            if insights:
                insights.append(f"類似ワークアウト比較: 前回({prev_date})から改善傾向")

        except Exception as e:
            logger.warning(f"Error generating comparison insights: {e}")

        return insights

    def _add_additional_comparisons(
        self,
        comparisons: list[dict[str, str]],
        current_additional: tuple[Any, ...],
        similar_additional: tuple[Any, ...] | None,
    ) -> None:
        """Add additional metric comparisons (power, stride, GCT, VO)."""
        # Power
        if current_additional[0]:
            if similar_additional and similar_additional[0]:
                power_diff = current_additional[0] - similar_additional[0]
                comparisons.append(
                    {
                        "metric": "平均パワー",
                        "current": f"{int(current_additional[0])} W",
                        "average": f"{int(similar_additional[0])} W",
                        "change": f"{int(power_diff):+} W",
                        "trend": (
                            "↗️ 効率向上"
                            if power_diff < 0
                            else ("➡️ 安定" if abs(power_diff) < 10 else "↗️ 改善")
                        ),
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": "平均パワー",
                        "current": f"{int(current_additional[0])} W",
                        "average": "N/A",
                        "change": "N/A",
                        "trend": "N/A",
                    }
                )

        # Stride (convert cm to m)
        if current_additional[1]:
            current_stride_m = current_additional[1] / 100
            if similar_additional and similar_additional[1]:
                similar_stride_m = similar_additional[1] / 100
                stride_diff = current_stride_m - similar_stride_m
                comparisons.append(
                    {
                        "metric": "平均ストライド",
                        "current": f"{current_stride_m:.2f} m",
                        "average": f"{similar_stride_m:.2f} m",
                        "change": f"{stride_diff:+.2f} m",
                        "trend": "↗️ 改善" if stride_diff > 0 else "➡️ 維持",
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": "平均ストライド",
                        "current": f"{current_stride_m:.2f} m",
                        "average": "N/A",
                        "change": "N/A",
                        "trend": "N/A",
                    }
                )

        # GCT
        if current_additional[2]:
            if similar_additional and similar_additional[2]:
                gct_diff = current_additional[2] - similar_additional[2]
                comparisons.append(
                    {
                        "metric": "接地時間",
                        "current": f"{int(current_additional[2])} ms",
                        "average": f"{int(similar_additional[2])} ms",
                        "change": f"{int(gct_diff):+} ms",
                        "trend": "↗️ 改善" if gct_diff < 0 else "➡️ 維持",
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": "接地時間",
                        "current": f"{int(current_additional[2])} ms",
                        "average": "N/A",
                        "change": "N/A",
                        "trend": "N/A",
                    }
                )

        # VO
        if current_additional[3]:
            if similar_additional and similar_additional[3]:
                vo_diff = current_additional[3] - similar_additional[3]
                comparisons.append(
                    {
                        "metric": "垂直振幅",
                        "current": f"{current_additional[3]:.2f} cm",
                        "average": f"{similar_additional[3]:.2f} cm",
                        "change": f"{vo_diff:+.2f} cm",
                        "trend": "↗️ 改善" if vo_diff < 0 else "➡️ 維持",
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": "垂直振幅",
                        "current": f"{current_additional[3]:.2f} cm",
                        "average": "N/A",
                        "change": "N/A",
                        "trend": "N/A",
                    }
                )

    def _add_recovery_rate_comparison(
        self,
        comparisons: list[dict[str, str]],
        activity_id: int,
        similar_ids: list[int],
    ) -> None:
        """Add recovery rate comparison for interval activities."""
        recovery_results = self.db_reader.execute_read_query(
            """
            SELECT
                AVG(CASE WHEN intensity_type IN ('ACTIVE', 'INTERVAL') THEN heart_rate END) as work_hr,
                AVG(CASE WHEN intensity_type IN ('REST', 'RECOVERY') THEN heart_rate END) as recovery_hr
            FROM splits
            WHERE activity_id = ?
            """,
            (activity_id,),
        )
        current_recovery = recovery_results[0] if recovery_results else None

        if current_recovery and current_recovery[0] and current_recovery[1]:
            current_recovery_rate = (current_recovery[1] / current_recovery[0]) * 100

            # Calculate for similar activities
            similar_recovery_rates = []
            for sim_id in similar_ids:
                sim_results = self.db_reader.execute_read_query(
                    """
                    SELECT
                        AVG(CASE WHEN intensity_type IN ('ACTIVE', 'INTERVAL') THEN heart_rate END) as work_hr,
                        AVG(CASE WHEN intensity_type IN ('REST', 'RECOVERY') THEN heart_rate END) as recovery_hr
                    FROM splits
                    WHERE activity_id = ?
                    """,
                    (sim_id,),
                )
                sim_recovery = sim_results[0] if sim_results else None

                if sim_recovery and sim_recovery[0] and sim_recovery[1]:
                    similar_recovery_rates.append(
                        (sim_recovery[1] / sim_recovery[0]) * 100
                    )

            if similar_recovery_rates:
                avg_similar_recovery = sum(similar_recovery_rates) / len(
                    similar_recovery_rates
                )
                recovery_diff = current_recovery_rate - avg_similar_recovery
                comparisons.append(
                    {
                        "metric": "Recovery回復率",
                        "current": f"{int(current_recovery_rate)}%",
                        "average": f"{int(avg_similar_recovery)}%",
                        "change": f"{int(recovery_diff):+}%",
                        "trend": (
                            "↗️ 改善"
                            if recovery_diff > 0
                            else ("➡️ 維持" if abs(recovery_diff) < 3 else "↘️ 要改善")
                        ),
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": "Recovery回復率",
                        "current": f"{int(current_recovery_rate)}%",
                        "average": "N/A",
                        "change": "N/A",
                        "trend": "N/A",
                    }
                )
