"""
Report Generator Worker

Reads performance data from DuckDB and generates final Markdown report.
Python Worker for report generation from section analyses.
"""

import json
import logging
from datetime import datetime
from typing import Any

import duckdb

from tools.database.db_reader import GarminDBReader
from tools.reporting.report_template_renderer import ReportTemplateRenderer

logger = logging.getLogger(__name__)


class ReportGeneratorWorker:
    """Python Worker for report generation from section analyses."""

    def __init__(self, db_path: str | None = None):
        """
        Initialize report generator worker.

        Args:
            db_path: DuckDB database path (default: uses environment variable)
        """
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        self.db_reader = GarminDBReader(db_path)
        self.renderer = ReportTemplateRenderer()

    def load_performance_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Load all performance data from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Complete performance data dict or None
        """
        logger.info("[1/4] Loading performance data from DuckDB...")

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load basic info and metrics from activities table
            result = conn.execute(
                """
                SELECT
                    activity_name,
                    location_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    temp_celsius,
                    relative_humidity_percent,
                    wind_speed_kmh,
                    gear_type,
                    gear_model
                FROM activities
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            if not result:
                conn.close()
                logger.warning(
                    f"Warning: No performance data found in DuckDB for activity {activity_id}"
                )
                return None

            # Load form efficiency statistics
            form_eff = conn.execute(
                """
                SELECT
                    gct_average, gct_std, gct_rating,
                    vo_average, vo_std, vo_rating,
                    vr_average, vr_std, vr_rating
                FROM form_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            # Load performance trends (support both 3-phase and 4-phase)
            # Check which columns exist in the schema
            schema_check = conn.execute(
                "PRAGMA table_info('performance_trends')"
            ).fetchall()
            column_names = [row[1] for row in schema_check]

            # Build query based on available columns
            if "recovery_avg_pace_seconds_per_km" in column_names:
                # 4-phase structure exists
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency, hr_drift_percentage, cadence_consistency, fatigue_pattern,
                        warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                        run_avg_pace_seconds_per_km, run_avg_hr, run_avg_power,
                        recovery_avg_pace_seconds_per_km, recovery_avg_hr,
                        cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            else:
                # Legacy 3-phase structure
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency, hr_drift_percentage, cadence_consistency, fatigue_pattern,
                        warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                        main_avg_pace_seconds_per_km, main_avg_hr, NULL,
                        NULL, NULL,
                        finish_avg_pace_seconds_per_km, finish_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

            # Load HR efficiency (includes training_type)
            hr_eff = conn.execute(
                """
                SELECT training_type
                FROM hr_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            # Load heart rate zone times (if table exists)
            try:
                hr_zone_times = conn.execute(
                    """
                    SELECT zone_number, time_in_zone_seconds
                    FROM heart_rate_zones
                    WHERE activity_id = ?
                    ORDER BY zone_number
                    """,
                    [activity_id],
                ).fetchall()
            except Exception:
                # Table may not exist in test databases
                hr_zone_times = []

            conn.close()

            # Load VO2 Max data (uses fallback to most recent data)
            vo2_max_dict = self.db_reader.get_vo2_max_data(activity_id)

            # Load lactate threshold data
            lactate_threshold_dict = self.db_reader.get_lactate_threshold_data(
                activity_id
            )

            # Build response data
            data: dict[str, Any] = {
                "activity_name": result[0],
                "location_name": result[1],
                "basic_metrics": {
                    "start_time": result[2],
                    "distance_km": result[3],
                    "duration_seconds": result[4],
                    "avg_pace_seconds_per_km": result[5],
                    "avg_heart_rate": result[6],
                },
                "weight_kg": None,  # Not stored in activities table
                "weather_data": {
                    "temp_celsius": result[7],
                    "relative_humidity_percent": result[8],
                    "wind_speed_kmh": result[9],
                },
                "gear_name": f"{result[10]} {result[11]}" if result[10] else None,
            }

            # Add form efficiency data if available
            if form_eff:
                data["form_efficiency"] = {
                    "gct_average": form_eff[0],
                    "gct_std": form_eff[1],
                    "gct_rating": form_eff[2],
                    "vo_average": form_eff[3],
                    "vo_std": form_eff[4],
                    "vo_rating": form_eff[5],
                    "vr_average": form_eff[6],
                    "vr_std": form_eff[7],
                    "vr_rating": form_eff[8],
                }

            # Add performance metrics if available
            if perf_trends:
                data["performance_metrics"] = {
                    "pace_consistency": perf_trends[0],
                    "hr_drift_percentage": perf_trends[1],
                    "cadence_consistency": perf_trends[2],
                    "fatigue_pattern": perf_trends[3],
                }
                data["warmup_metrics"] = {
                    "avg_pace_seconds_per_km": perf_trends[4],
                    "avg_hr": perf_trends[5],
                }
                # Check if recovery data exists (4-phase) or not (3-phase)
                if perf_trends[9] is not None:
                    # 4-phase structure (interval training)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "avg_power": perf_trends[8],
                        "pace_consistency": perf_trends[0],
                    }
                    data["recovery_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[9],
                        "avg_hr": perf_trends[10],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[11],
                        "avg_hr": perf_trends[12],
                        "fatigue_pattern": perf_trends[3],
                    }
                else:
                    # 3-phase structure (regular run)
                    # Map to new naming: run (was main), cooldown (was finish)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "avg_power": perf_trends[8],
                        "pace_consistency": perf_trends[0],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[11],
                        "avg_hr": perf_trends[12],
                        "fatigue_pattern": perf_trends[3],
                    }
                    # Legacy naming for backward compatibility
                    data["main_metrics"] = data["run_metrics"]
                    data["finish_metrics"] = data["cooldown_metrics"]

            # Add training type if available
            if hr_eff:
                data["training_type"] = hr_eff[0]

            # Add VO2 Max data if available
            if vo2_max_dict:
                data["vo2_max_data"] = vo2_max_dict

            # Add lactate threshold data if available
            if lactate_threshold_dict:
                data["lactate_threshold_data"] = lactate_threshold_dict

            # Add similar workouts comparison (Phase 3)
            # Determine comparison pace based on training type
            comparison_pace, pace_source = self._get_comparison_pace(data)

            current_metrics = {
                "avg_pace": comparison_pace,
                "avg_hr": data["basic_metrics"]["avg_heart_rate"],
                "pace_source": pace_source,
            }
            data["similar_workouts"] = self._load_similar_workouts(
                activity_id, current_metrics
            )

            # Generate workout insight based on comparison data
            if data["similar_workouts"]:
                data["similar_workouts"]["insight"] = self._generate_workout_insight(
                    data["similar_workouts"], data.get("training_type", "aerobic_base")
                )

            # Generate reference info (VO2 Max + Threshold pace + FTP for Interval)
            data["reference_info"] = self._generate_reference_info(
                data.get("vo2_max_data"),
                data.get("lactate_threshold_data"),
                data.get("training_type", "aerobic_base"),
            )

            # Add pace-corrected form efficiency (Phase 4)
            if form_eff:
                data["form_efficiency_pace_corrected"] = (
                    self._calculate_pace_corrected_form_efficiency(
                        data["basic_metrics"]["avg_pace_seconds_per_km"],
                        data["form_efficiency"],
                    )
                )

            # Load splits and generate Mermaid graph data
            data["splits"] = self._load_splits(activity_id)
            data["mermaid_data"] = self._generate_mermaid_data(data.get("splits"))

            # ========== NEW: Phase 2 Enhancements ==========

            # 1. Calculate training type category
            training_type = data.get("training_type", "")
            training_type_category = self._get_training_type_category(training_type)
            data["training_type_category"] = training_type_category

            # 2. Calculate physiological indicators (for tempo/threshold and interval)
            if training_type_category in ["tempo_threshold", "interval_sprint"]:
                physiological_indicators = self._calculate_physiological_indicators(
                    training_type_category,
                    data.get("vo2_max_data"),
                    data.get("lactate_threshold_data"),
                    data.get("run_metrics", {}),
                    hr_zone_times,
                )
                data.update(physiological_indicators)

            # 3. Generate evaluation target text
            data["target_segments_description"] = self._get_evaluation_target_text(
                training_type_category
            )

            # 4. Generate interval graph analysis (for interval only)
            if training_type_category == "interval_sprint" and data.get("splits"):
                data["interval_graph_analysis"] = self._generate_mermaid_analysis(
                    data["splits"], training_type_category
                )

            return data

        except Exception as e:
            logger.error(f"Error loading performance data: {e}")
            return None

    def _generate_mermaid_data(
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

    def _generate_mermaid_analysis(
        self, splits: list[dict[str, Any]], training_type_category: str
    ) -> str | None:
        """
        Generate Work/Recovery transition analysis for interval workouts.

        Args:
            splits: List of split dictionaries with intensity_type
            training_type_category: Training type category

        Returns:
            3-4 bullet point analysis text (Japanese) or None for non-interval

        Examples:
            >>> splits = [
            ...     {"index": 1, "intensity_type": "warmup", "pace_seconds_per_km": 420, "heart_rate": 135},
            ...     {"index": 2, "intensity_type": "active", "pace_seconds_per_km": 250, "heart_rate": 175, "power": 320},
            ...     {"index": 3, "intensity_type": "rest", "pace_seconds_per_km": 450, "heart_rate": 140, "power": 180},
            ...     {"index": 4, "intensity_type": "active", "pace_seconds_per_km": 248, "heart_rate": 178, "power": 325},
            ... ]
            >>> worker = ReportGeneratorWorker()
            >>> analysis = worker._generate_mermaid_analysis(splits, "interval_sprint")
            >>> "Work区間" in analysis
            True
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

    def _generate_hr_zone_pie_data(self, activity_id: int) -> str | None:
        """
        Generate Mermaid pie chart data for heart rate zones.

        Args:
            activity_id: Activity ID

        Returns:
            Mermaid pie chart data string or None if no data available
        """
        try:
            # Query heart rate zone data from DuckDB
            import duckdb

            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    zone_number,
                    zone_percentage
                FROM heart_rate_zones
                WHERE activity_id = ?
                AND zone_percentage > 0
                ORDER BY zone_number
                """,
                [activity_id],
            ).fetchall()

            conn.close()

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

    def _load_splits(self, activity_id: int) -> list[dict[str, Any]]:
        """
        Load splits from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries with index, pace, HR, etc.
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            result = conn.execute(
                """
                SELECT
                    split_index AS index,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    intensity_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                logger.warning(f"No splits found for activity {activity_id}")
                return []

            # Convert to dict format expected by template
            splits = []
            for row in result:
                pace_seconds = row[1]
                if pace_seconds and pace_seconds > 0:
                    pace_formatted = self._format_pace(pace_seconds)
                else:
                    pace_formatted = "N/A"

                # Normalize intensity_type (Garmin uses uppercase)
                raw_intensity_type = row[11]
                intensity_type = None
                if raw_intensity_type:
                    intensity_upper = raw_intensity_type.upper()
                    if intensity_upper == "WARMUP":
                        intensity_type = "warmup"
                    elif intensity_upper == "INTERVAL":
                        intensity_type = "active"
                    elif intensity_upper == "RECOVERY":
                        intensity_type = "rest"
                    elif intensity_upper == "COOLDOWN":
                        intensity_type = "cooldown"
                    else:
                        intensity_type = raw_intensity_type.lower()

                splits.append(
                    {
                        "index": row[0],
                        "pace_seconds_per_km": pace_seconds,
                        "pace_formatted": pace_formatted,
                        "heart_rate": row[2],
                        "cadence": row[3],
                        "power": row[4],
                        "stride_length": (
                            row[5] / 100 if row[5] else None
                        ),  # Convert cm to m
                        "ground_contact_time": row[6],
                        "vertical_oscillation": row[7],
                        "vertical_ratio": row[8],
                        "elevation_gain": row[9],
                        "elevation_loss": row[10],
                        "intensity_type": intensity_type,
                    }
                )

            logger.info(f"Loaded {len(splits)} splits for activity {activity_id}")
            return splits

        except Exception as e:
            logger.error(f"Error loading splits: {e}", exc_info=True)
            return []

    def _format_pace(self, pace_seconds_per_km: float) -> str:
        """Format pace as MM:SS/km.

        Args:
            pace_seconds_per_km: Pace in seconds per kilometer

        Returns:
            Formatted pace string (e.g., "4:30/km")
        """
        minutes = int(pace_seconds_per_km / 60)
        seconds = int(pace_seconds_per_km % 60)
        return f"{minutes}:{seconds:02d}/km"

    def _get_activity_type_display(self, training_type: str) -> dict[str, str]:
        """Map training_type to Japanese display name and English subtitle.

        Args:
            training_type: DuckDB training_type value

        Returns:
            dict with keys: "ja" (Japanese name), "en" (English name), "description"
        """
        mapping = {
            "recovery": {
                "ja": "リカバリーラン",
                "en": "Recovery Run",
                "description": "軽い有酸素運動で疲労回復を促進",
            },
            "aerobic_base": {
                "ja": "有酸素ベース走",
                "en": "Aerobic Base",
                "description": "心拍ゾーン2-3中心の中強度トレーニング。有酸素能力の基盤構築に最適な強度です。",
            },
            "tempo": {
                "ja": "テンポラン",
                "en": "Tempo Run",
                "description": "心拍ゾーン3-4の中高強度。閾値走より少し楽なペースで持久力を強化",
            },
            "lactate_threshold": {
                "ja": "乳酸閾値トレーニング",
                "en": "Lactate Threshold",
                "description": "3フェーズ構成（ウォームアップ-メイン-クールダウン）で、閾値ペースを維持する持久力強化トレーニング。Zone 4中心で乳酸処理能力を向上させることが目的です。",
            },
            "vo2max": {
                "ja": "VO2 Maxトレーニング",
                "en": "VO2 Max Training",
                "description": "最大酸素摂取量向上を目的とした高強度インターバル",
            },
            "anaerobic_capacity": {
                "ja": "無酸素容量トレーニング",
                "en": "Anaerobic Capacity",
                "description": "短時間高強度で無酸素能力を強化",
            },
            "speed": {
                "ja": "スピードトレーニング",
                "en": "Speed Training",
                "description": "短距離スプリントでスピードとパワーを強化",
            },
            "interval_training": {
                "ja": "インターバルトレーニング",
                "en": "Interval Training",
                "description": "1km×5本のWorkセグメントをZone 4-5（閾値〜最大心拍）で実施し、400mのRecoveryで回復する高強度トレーニング。VO2 max向上とスピード持久力の強化が目的です。",
            },
        }
        return mapping.get(
            training_type,
            {
                "ja": "その他のトレーニング",
                "en": "Other Training",
                "description": "分類不明のトレーニング",
            },
        )

    def _get_training_type_category(self, training_type: str) -> str:
        """Map training_type to template category for conditional logic.

        Args:
            training_type: DuckDB training_type value

        Returns:
            Category string:
            - "low_moderate": recovery, aerobic_base, aerobic_endurance, unknown
            - "tempo_threshold": tempo, lactate_threshold
            - "interval_sprint": vo2max, anaerobic_capacity, speed, interval_training

        This categorization is used for:
        - Showing/hiding physiological indicators summary
        - Selecting appropriate comparison pace (main_set vs overall)
        - Determining evaluation focus (overall vs specific phases)
        """
        interval_sprint = {
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",
        }
        tempo_threshold = {"tempo", "lactate_threshold"}

        if training_type in interval_sprint:
            return "interval_sprint"
        elif training_type in tempo_threshold:
            return "tempo_threshold"
        else:
            # Default to low_moderate for recovery, aerobic_base, and unknown types
            return "low_moderate"

    def _calculate_physiological_indicators(
        self,
        training_type_category: str,
        vo2_max_data: dict | None,
        lactate_threshold_data: dict | None,
        run_metrics: dict,
        hr_zone_times: list[tuple] | None = None,
    ) -> dict:
        """Calculate physiological indicators for tempo/threshold/interval workouts.

        Args:
            training_type_category: Training type category from _get_training_type_category
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database
            run_metrics: Run/main phase metrics
            hr_zone_times: List of (zone_number, time_in_zone_seconds) tuples from heart_rate_zones table

        Returns:
            Dictionary with physiological indicators (empty dict if low_moderate or missing data)

        Indicators:
            - vo2_max_utilization: Percentage of VO2 Max being utilized (0-100%)
            - vo2_max_utilization_eval: Evaluation text
            - threshold_pace_formatted: Threshold pace in MM:SS/km format
            - threshold_pace_comparison: Comparison text vs actual pace
            - ftp_percentage: Percentage of FTP (Functional Threshold Power)
            - work_avg_power: Average power during Work segments
            - zone_4_ratio: Percentage of time in Zone 4 (for threshold only)
        """
        # Only calculate for tempo_threshold and interval_sprint
        if training_type_category == "low_moderate":
            return {}

        # Check that at least run_metrics is available
        if not run_metrics:
            return {}

        result = {}

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
            # Empirical formula: vVO2max (km/h) ≈ VO2max / 3.5
            vo2_max_speed_kmh = vo2_max_value / 3.5
            vo2_max_pace_seconds_per_km = 3600 / vo2_max_speed_kmh

            # Utilization = VO2max pace / current pace * 100
            vo2_max_utilization = (vo2_max_pace_seconds_per_km / target_pace) * 100
            result["vo2_max_utilization"] = round(vo2_max_utilization, 1)

            # Evaluation text
            if vo2_max_utilization >= 90:
                result["vo2_max_utilization_eval"] = "非常に高強度"
            elif vo2_max_utilization >= 80:
                result["vo2_max_utilization_eval"] = "高強度（閾値〜VO2max）"
            elif vo2_max_utilization >= 70:
                result["vo2_max_utilization_eval"] = "中高強度（テンポ〜閾値）"
            else:
                result["vo2_max_utilization_eval"] = "中強度"

        # Format threshold pace and comparison
        if threshold_speed and target_pace:
            threshold_pace_seconds_per_km = 1000 / threshold_speed
            result["threshold_pace_formatted"] = self._format_pace(
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
            result["ftp_percentage"] = round((work_avg_power / ftp) * 100, 1)
            result["work_avg_power"] = round(work_avg_power, 0)

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

    def _get_comparison_pace(self, performance_data: dict) -> tuple[float, str]:
        """
        Determine which pace to use for similarity comparison.

        Args:
            performance_data: Performance data dict with training_type, run_metrics, basic_metrics

        Returns:
            tuple: (pace_seconds_per_km, pace_source)
            - pace_source: "main_set" | "overall"

        Logic:
            - Structured workouts (tempo, lactate_threshold, vo2max, anaerobic_capacity, speed, interval_training):
              → Use run_metrics.avg_pace_seconds_per_km (if available)
            - Recovery/base/unknown:
              → Use basic_metrics.avg_pace_seconds_per_km
        """
        training_type = performance_data.get("training_type", "unknown")
        structured_types = {
            "tempo",
            "lactate_threshold",
            "vo2max",
            "anaerobic_capacity",
            "speed",
            "interval_training",  # Added for Work-only comparison
        }

        # Use main set pace for structured workouts (if available)
        if training_type in structured_types:
            run_metrics = performance_data.get("run_metrics")
            if run_metrics and run_metrics.get("avg_pace_seconds_per_km"):
                return (run_metrics["avg_pace_seconds_per_km"], "main_set")

        # Fallback: use overall average pace
        return (performance_data["basic_metrics"]["avg_pace_seconds_per_km"], "overall")

    def _get_evaluation_target_text(self, training_type_category: str) -> str:
        """
        Get evaluation target description text based on training type.

        Args:
            training_type_category: "low_moderate" | "tempo_threshold" | "interval_sprint"

        Returns:
            Japanese description of evaluation target segments

        Examples:
            >>> worker = ReportGeneratorWorker()
            >>> worker._get_evaluation_target_text("interval_sprint")
            "Workセグメント5本のみ（インターバル走は高強度区間のパフォーマンスを重視）"
            >>> worker._get_evaluation_target_text("tempo_threshold")
            "メイン区間（Split 3-6）のみ（閾値走は高強度区間のパフォーマンスを重視）"
        """
        if training_type_category == "interval_sprint":
            return "Workセグメント5本のみ（インターバル走は高強度区間のパフォーマンスを重視）"
        elif training_type_category == "tempo_threshold":
            return "メイン区間（Split 3-6）のみ（閾値走は高強度区間のパフォーマンスを重視）"
        else:
            # For low_moderate, no specific target (all splits evaluated)
            return ""

    def _load_similar_workouts(
        self, activity_id: int, current_metrics: dict
    ) -> dict | None:
        """Load similar workouts comparison using MCP tool.

        Returns None if insufficient data or error occurs.
        Template will gracefully handle None with "類似ワークアウトが見つかりませんでした。"

        Args:
            activity_id: Activity ID to find similar workouts for
            current_metrics: Dictionary with 'avg_pace', 'avg_hr', and 'pace_source' keys

        Returns:
            Dictionary with comparison data or None
        """
        try:
            # Import WorkoutComparator from correct location
            from tools.rag.queries.comparisons import WorkoutComparator

            comparator = WorkoutComparator()
            result = comparator.find_similar_workouts(
                activity_id=activity_id,
                distance_tolerance=0.10,
                pace_tolerance=0.10,
                terrain_match=True,
                limit=10,
            )

            # Extract workouts list from result (correct key name)
            similar = result.get("similar_activities", [])

            if not similar or len(similar) < 3:
                logger.warning(
                    f"Insufficient similar workouts for activity {activity_id}"
                )
                return None

            # Calculate average differences from top 3
            top_3 = similar[:3]
            avg_pace_diff = sum([w["pace_diff"] for w in top_3]) / 3
            avg_hr_diff = sum([w["hr_diff"] for w in top_3]) / 3

            pace_diff = avg_pace_diff
            hr_diff = avg_hr_diff

            avg_similar_pace = current_metrics["avg_pace"] - avg_pace_diff
            avg_similar_hr = current_metrics["avg_hr"] - avg_hr_diff

            # Determine which pace to use for comparison
            pace_source = current_metrics.get("pace_source", "overall")

            # For main_set comparison, filter by intensity_type
            if pace_source == "main_set":
                intensity_filter = "AND intensity_type IN ('ACTIVE', 'INTERVAL')"
            else:
                intensity_filter = ""

            # Get additional metrics from splits table
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Get current activity metrics (filtered by intensity_type if main_set)
            current_additional = conn.execute(
                f"""
                SELECT
                    AVG(power) as avg_power,
                    AVG(stride_length) as avg_stride_cm,
                    AVG(ground_contact_time) as avg_gct,
                    AVG(vertical_oscillation) as avg_vo
                FROM splits
                WHERE activity_id = ? {intensity_filter}
                """,
                [activity_id],
            ).fetchone()

            # Get similar activities metrics (same filtering)
            similar_ids = [w["activity_id"] for w in top_3]
            similar_additional = conn.execute(
                f"""
                SELECT
                    AVG(power) as avg_power,
                    AVG(stride_length) as avg_stride_cm,
                    AVG(ground_contact_time) as avg_gct,
                    AVG(vertical_oscillation) as avg_vo
                FROM splits
                WHERE activity_id IN ({",".join("?" * len(similar_ids))}) {intensity_filter}
                """,
                similar_ids,
            ).fetchone()

            # Format comparison table
            comparisons = [
                {
                    "metric": "平均ペース",
                    "current": self._format_pace(current_metrics["avg_pace"]),
                    "average": self._format_pace(avg_similar_pace),
                    "change": (
                        f"+{abs(int(pace_diff))}秒速い"
                        if pace_diff < 0
                        else f"-{int(pace_diff)}秒遅い"
                    ),
                    "trend": (
                        "↗️ 改善"
                        if pace_diff < 0
                        else ("↘️ 悪化" if pace_diff > 5 else "➡️ 同等")
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
                        else ("⚠️ 高い" if hr_diff > 0 else "✅ 低い")
                    ),
                },
            ]

            # Add additional metrics if available (Option A: show N/A if missing)
            if current_additional:
                # Power - show for all training types
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
                                    else "➡️ 安定" if abs(power_diff) < 10 else "↗️ 改善"
                                ),
                            }
                        )
                    else:
                        # Option A: Show N/A if similar activities lack data
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

            # Add training-type-specific metrics
            try:
                hr_data = self.db_reader.get_hr_efficiency_analysis(activity_id)
                training_type = hr_data.get("training_type") if hr_data else None

                # Pace variability coefficient - now for ALL training types
                current_pace_cv = conn.execute(
                    f"""
                    SELECT STDDEV(pace_seconds_per_km) / AVG(pace_seconds_per_km) as pace_cv
                    FROM splits
                    WHERE activity_id = ? {intensity_filter}
                    """,
                    [activity_id],
                ).fetchone()[0]

                # Calculate average pace CV for similar activities
                similar_pace_cvs = []
                for sim_id in similar_ids:
                    sim_cv = conn.execute(
                        f"""
                        SELECT STDDEV(pace_seconds_per_km) / AVG(pace_seconds_per_km) as pace_cv
                        FROM splits
                        WHERE activity_id = ? {intensity_filter}
                        """,
                        [sim_id],
                    ).fetchone()[0]

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
                    # Get Work and Recovery segments from splits (using intensity_type)
                    # Recovery rate = Average Recovery HR / Average Work HR * 100
                    current_recovery = conn.execute(
                        """
                        SELECT
                            AVG(CASE WHEN intensity_type IN ('ACTIVE', 'INTERVAL') THEN heart_rate END) as work_hr,
                            AVG(CASE WHEN intensity_type IN ('REST', 'RECOVERY') THEN heart_rate END) as recovery_hr
                        FROM splits
                        WHERE activity_id = ?
                        """,
                        [activity_id],
                    ).fetchone()

                    if current_recovery and current_recovery[0] and current_recovery[1]:
                        current_recovery_rate = (
                            current_recovery[1] / current_recovery[0]
                        ) * 100

                        # Calculate for similar activities
                        similar_recovery_rates = []
                        for sim_id in similar_ids:
                            sim_recovery = conn.execute(
                                """
                                SELECT
                                    AVG(CASE WHEN intensity_type IN ('ACTIVE', 'INTERVAL') THEN heart_rate END) as work_hr,
                                    AVG(CASE WHEN intensity_type IN ('REST', 'RECOVERY') THEN heart_rate END) as recovery_hr
                                FROM splits
                                WHERE activity_id = ?
                                """,
                                [sim_id],
                            ).fetchone()

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
                                        else (
                                            "➡️ 維持"
                                            if abs(recovery_diff) < 3
                                            else "↘️ 要改善"
                                        )
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
            elevation_data = conn.execute(
                """
                SELECT SUM(elevation_gain) as total_gain
                FROM splits
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()
            elevation_gain = (
                elevation_data[0] if elevation_data and elevation_data[0] else 0
            )

            conn.close()

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

                # If pace is faster (pace_diff < 0) and power is lower (power_diff < 0)
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

            # Distance description (round to nearest km)
            distance_rounded = round(target_distance)
            distance_desc = f"{distance_rounded}km前後"

            # Pace description based on training type
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
            pace_desc = training_type_map.get(training_type_raw or "", "ペース類似")

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
            }

        except Exception as e:
            logger.warning(f"Could not load similar workouts: {e}")
            return None

    def _generate_workout_insight(
        self, similar_workouts: dict, training_type: str
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
                # Extract numeric changes
                pace_change = self._extract_numeric_change(pace_comp["change"])
                power_change = self._extract_numeric_change(power_comp["change"])

                if pace_change < 0 and power_change < 0:  # Faster pace, lower power
                    # Calculate efficiency improvement percentage
                    avg_power = self._extract_numeric_value(power_comp["average"])
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

            if pace_comp and self._extract_numeric_change(pace_comp["change"]) < 0:
                pace_change = abs(self._extract_numeric_change(pace_comp["change"]))
                improvements.append(f"Workペース+{pace_change:.0f}秒速")

            if power_comp and self._extract_numeric_change(power_comp["change"]) > 0:
                power_change = self._extract_numeric_change(power_comp["change"])
                improvements.append(f"パワー+{power_change:.0f}W")

            if stride_comp and self._extract_numeric_change(stride_comp["change"]) > 0:
                stride_change = self._extract_numeric_change(stride_comp["change"])
                improvements.append(f"ストライド+{stride_change * 100:.0f}cm向上")

            if improvements:
                improvements_text = "、".join(improvements)
                return f"{improvements_text} = **高強度下でもフォーム効率とパワー出力を改善** ✅"

        # Threshold pattern: Same pace + Lower HR = Efficiency improvement
        elif training_type in ["lactate_threshold", "tempo"]:
            pace_comp = comparisons.get("メイン平均ペース")
            hr_comp = comparisons.get("メイン平均心拍")

            if pace_comp and hr_comp:
                pace_change = self._extract_numeric_change(pace_comp["change"])
                hr_change = self._extract_numeric_change(hr_comp["change"])

                if abs(pace_change) <= 1 and hr_change < 0:  # Same pace, lower HR
                    avg_hr = self._extract_numeric_value(hr_comp["average"])
                    if avg_hr and avg_hr > 0:
                        efficiency_pct = abs(hr_change / avg_hr * 100)
                        return f"同じペースで心拍{abs(hr_change):.0f}bpm低下 = **閾値での効率が{efficiency_pct:.1f}%向上** ✅"

        # Fallback: Generic improvement message
        return "複数指標で改善が見られます"

    def _extract_numeric_change(self, change_text: str) -> float:
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
        import re

        # Extract number with optional sign
        match = re.search(r"([+-]?\d+\.?\d*)", change_text)
        if not match:
            return 0.0

        value = float(match.group(1))

        # Invert sign for "速い" (faster is better, so negative)
        if "速い" in change_text:
            value = -abs(value)

        return value

    def _extract_numeric_value(self, value_text: str) -> float | None:
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
        import re

        match = re.search(r"(\d+\.?\d*)", value_text)
        if match:
            return float(match.group(1))
        return None

    def _generate_reference_info(
        self,
        vo2_max_data: dict | None,
        lactate_threshold_data: dict | None,
        training_type: str = "aerobic_base",
    ) -> str:
        """
        Generate reference information text for VO2 Max and lactate threshold.

        Example output:
            "> **参考**: VO2 Max 52.3 ml/kg/min（優秀）、閾値ペース 4:35/km"
            "> **参考**: VO2 Max 52.3 ml/kg/min（優秀）、閾値ペース 4:35/km、FTP 285W" (for Interval)

        Args:
            vo2_max_data: VO2 Max data from database
            lactate_threshold_data: Lactate threshold data from database
            training_type: Training type (used to determine if FTP should be shown)

        Returns:
            Formatted reference info text
        """
        parts = []

        # VO2 Max
        if vo2_max_data:
            vo2_value = vo2_max_data.get("precise_value") or vo2_max_data.get("value")
            vo2_category = vo2_max_data.get("category")
            if vo2_value:
                # Only include category if it's not 0 or None
                if vo2_category and vo2_category != 0 and vo2_category != "N/A":
                    parts.append(f"VO2 Max {vo2_value} ml/kg/min（{vo2_category}）")
                else:
                    parts.append(f"VO2 Max {vo2_value} ml/kg/min")

        # Lactate threshold pace
        if lactate_threshold_data:
            threshold_speed = lactate_threshold_data.get("speed_mps")
            if threshold_speed and threshold_speed > 0:
                # Convert m/s to min/km
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

    def _calculate_pace_corrected_form_efficiency(
        self, avg_pace_seconds_per_km: float, form_eff: dict
    ) -> dict:
        """Calculate pace-corrected form efficiency scores.

        Formulas from planning.md Appendix C:
        - GCT baseline: 230 + (pace - 240) * 0.22 ms
        - VO baseline: 6.8 + (pace - 240) * 0.004 cm
        - VR: No correction, absolute threshold 8.0-9.5%

        Args:
            avg_pace_seconds_per_km: Average pace in seconds per km
            form_eff: Form efficiency dictionary with gct_average, vo_average, vr_average

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

        return {
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

    def _build_form_efficiency_table(self, pace_corrected_data: dict) -> dict[str, Any]:
        """Build form efficiency table structure for template rendering.

        Transforms pace-corrected form efficiency data into table format
        compatible with BALANCED template requirements.

        Args:
            pace_corrected_data: Output from _calculate_pace_corrected_form_efficiency()

        Returns:
            Dictionary with overall_form_score and form_efficiency_table array
        """
        table = []

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

        # Calculate overall form score (average of ratings)
        avg_rating = (gct["rating_score"] + vo["rating_score"] + vr["rating_score"]) / 3
        rating_stars = "★" * int(avg_rating) + "☆" * (5 - int(avg_rating))
        overall_form_score = f"{rating_stars} {avg_rating:.1f}/5.0"

        return {
            "overall_form_score": overall_form_score,
            "form_efficiency_table": table,
        }

    def load_section_analyses(
        self, activity_id: int, performance_data: dict[str, Any] | None = None
    ) -> dict[str, dict[str, Any]] | None:
        """
        Load section analyses from DuckDB matching actual data structures.

        Actual structure in DuckDB:
        - efficiency: {"efficiency": "...", "evaluation": "..."}  (Agent text only in new format)
        - environment: {"environmental": "..."}
        - phase: {"warmup_evaluation": "...", "run_evaluation": "...", "cooldown_evaluation": "..."}
        - split: {"analyses": {...}}
        - summary: {"activity_type": "...", "summary": "...", "recommendations": "..."}

        Args:
            activity_id: Activity ID
            performance_data: Optional performance data containing pace_corrected calculations

        Returns:
            Section analyses dict or None
        """
        logger.info("[2/4] Loading section analyses from DuckDB...")

        analyses = {}

        # Load efficiency analysis
        efficiency_data = self.db_reader.get_section_analysis(activity_id, "efficiency")
        if efficiency_data:
            # Check if we have pace-corrected data to build the table
            if (
                performance_data
                and "form_efficiency_pace_corrected" in performance_data
            ):
                # Build table structure from pace-corrected data
                table_data = self._build_form_efficiency_table(
                    performance_data["form_efficiency_pace_corrected"]
                )

                # Merge table with agent text (efficiency_text, hr_efficiency_text)
                analyses["efficiency"] = {
                    **table_data,  # overall_form_score, form_efficiency_table
                    "efficiency_text": efficiency_data.get("efficiency", ""),
                    "hr_efficiency_text": efficiency_data.get(
                        "evaluation", efficiency_data.get("hr_efficiency_text", "")
                    ),
                }
            elif "form_efficiency_table" in efficiency_data:
                # Legacy: Agent provided full structured format
                analyses["efficiency"] = efficiency_data
            elif "efficiency" in efficiency_data:
                # New format: Agent text only, but no performance data to build table
                analyses["efficiency"] = efficiency_data
            else:
                # Unknown format - use as-is
                analyses["efficiency"] = efficiency_data
        else:
            logger.warning("Warning: efficiency section analysis missing")

        # Load environment analysis (key is "environmental" not "environment_analysis")
        environment_data = self.db_reader.get_section_analysis(
            activity_id, "environment"
        )
        if environment_data:
            analyses["environment_analysis"] = environment_data.get("environmental", {})
        else:
            logger.warning("Warning: environment section analysis missing")

        # Load phase analysis - pass through as-is (flat structure)
        phase_data = self.db_reader.get_section_analysis(activity_id, "phase")
        if phase_data:
            # Pass through the flat structure from DuckDB directly
            # Template expects: warmup_evaluation, run_evaluation, recovery_evaluation, cooldown_evaluation
            analyses["phase_evaluation"] = phase_data
        else:
            logger.warning("Warning: phase section analysis missing")

        # Load split analysis (includes both "analyses" and "highlights")
        split_data = self.db_reader.get_section_analysis(activity_id, "split")
        if split_data:
            analyses["split_analysis"] = split_data
        else:
            logger.warning("Warning: split section analysis missing or empty")

        # Load summary analysis
        summary_data = self.db_reader.get_section_analysis(activity_id, "summary")
        if summary_data:
            # Parse key_strengths and improvement_areas if they are strings
            # (Agent may save them as newline-separated strings instead of lists)
            if "key_strengths" in summary_data and isinstance(
                summary_data["key_strengths"], str
            ):
                summary_data["key_strengths"] = [
                    line.strip()
                    for line in summary_data["key_strengths"].split("\n\n")
                    if line.strip()
                ]

            if "improvement_areas" in summary_data and isinstance(
                summary_data["improvement_areas"], str
            ):
                summary_data["improvement_areas"] = [
                    line.strip()
                    for line in summary_data["improvement_areas"].split("\n\n")
                    if line.strip()
                ]

            analyses["summary"] = summary_data
        else:
            logger.warning("Warning: summary section analysis missing")

        if not analyses:
            logger.warning("Warning: No section analyses found in DuckDB")
            return None

        return analyses

    def load_splits_data(self, activity_id: int) -> list[dict[str, Any]] | None:
        """
        Load splits data from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries or None
        """
        logger.info("[2.5/4] Loading splits data from DuckDB...")

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load splits data from splits table
            result = conn.execute(
                """
                SELECT
                    split_index,
                    distance,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    pace_str,
                    intensity_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

            if not result:
                logger.warning(
                    f"Warning: No splits data found in DuckDB for activity {activity_id}"
                )
                return None

            splits = []
            for row in result:
                splits.append(
                    {
                        "index": row[0],
                        "distance": row[1],
                        "pace_seconds_per_km": row[2],
                        "pace_formatted": (
                            row[12] if row[12] else "N/A"
                        ),  # Use pace_str from DB
                        "heart_rate": row[3],
                        "cadence": row[4],
                        "power": row[5],
                        "stride_length": (
                            row[6] / 100 if row[6] else None
                        ),  # Convert cm to m
                        "ground_contact_time": row[7],
                        "vertical_oscillation": row[8],
                        "vertical_ratio": row[9],
                        "elevation_gain": row[10],
                        "elevation_loss": row[11],
                        "intensity_type": row[13],
                    }
                )

            return splits

        except Exception as e:
            logger.error(f"Error loading splits data: {e}")
            return None

    def _generate_comparison_insights(
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
            import duckdb

            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Get current activity metrics
            current = conn.execute(
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
                [activity_id],
            ).fetchone()

            if not current:
                conn.close()
                return insights

            current_date, current_hr, current_pace, current_dist, current_gct = current

            # Find most recent similar workout (within ±10% pace and distance)
            previous = conn.execute(
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
                [
                    activity_id,
                    current_date,
                    current_pace,
                    current_pace,
                    current_dist,
                    current_dist,
                ],
            ).fetchone()

            conn.close()

            if not previous:
                return insights

            prev_id, prev_date, prev_hr, prev_pace, prev_gct = previous

            # Compare heart rate (lower is better at same pace)
            if current_hr and prev_hr:
                hr_diff = current_hr - prev_hr
                if hr_diff <= -1:  # At least 1 bpm improvement
                    insights.append(
                        f"**心拍効率向上**: 同ペースで前回比{hr_diff}bpm（有酸素能力向上）✅"
                    )

            # Compare GCT (lower is better)
            if current_gct and prev_gct:
                gct_diff = current_gct - prev_gct
                gct_pct = (gct_diff / prev_gct) * 100 if prev_gct > 0 else 0
                if gct_diff <= -1:  # At least 1ms improvement
                    insights.append(
                        f"**GCT改善**: 前回比{gct_diff:.1f}ms（効率{abs(gct_pct):.1f}%向上）✅"
                    )

            # Compare pace (faster is better at same HR)
            if current_pace and prev_pace:
                pace_diff = current_pace - prev_pace
                if pace_diff < -2 and abs(hr_diff) <= 2:  # Faster with same HR
                    insights.append(
                        f"**ペース向上**: 前回比{abs(pace_diff):.1f}秒/km速く、心拍効率も改善✅"
                    )

            # Add general comparison note
            if insights:
                insights.append(f"類似ワークアウト比較: 前回({prev_date})から改善傾向")

        except Exception as e:
            logger.warning(f"Error generating comparison insights: {e}")

        return insights

    def generate_report(
        self, activity_id: int, date: str | None = None
    ) -> dict[str, Any]:
        """
        Generate final report from performance.json and section analyses.

        Args:
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD format)

        Returns:
            Report generation result with path
        """
        # Resolve date if not provided
        if not date:
            date = self.db_reader.get_activity_date(activity_id)
            if not date:
                raise ValueError(f"Could not resolve date for activity {activity_id}")

        # Load data
        performance_data = self.load_performance_data(activity_id)
        if not performance_data:
            raise ValueError(f"No performance data found for activity {activity_id}")

        section_analyses = self.load_section_analyses(activity_id, performance_data)

        if not section_analyses:
            raise ValueError(
                f"No section analyses found for activity {activity_id}. Cannot generate report."
            )

        # Load splits data for split analysis基本データ表示
        splits_data = self.load_splits_data(activity_id)

        # Generate workout comparison insights if summary exists
        if "summary" in section_analyses and section_analyses["summary"]:
            try:
                # Get comparison data from previous similar workout
                insights = self._generate_comparison_insights(
                    activity_id, performance_data
                )

                # Add insights to key_strengths
                if insights and "key_strengths" in section_analyses["summary"]:
                    # Insert insights at the beginning of key_strengths
                    section_analyses["summary"]["key_strengths"] = (
                        insights + section_analyses["summary"]["key_strengths"]
                    )
            except Exception as e:
                logger.warning(f"Could not generate workout insights: {e}")

        logger.info("[3/4] Generating report from section analyses...")

        # Format pace values for display
        def format_pace(pace_seconds_per_km):
            if pace_seconds_per_km is None or pace_seconds_per_km == 0:
                return "N/A"
            minutes = int(pace_seconds_per_km // 60)
            seconds = int(pace_seconds_per_km % 60)
            return f"{minutes}:{seconds:02d}"

        # Add formatted pace values
        if "warmup_metrics" in performance_data:
            performance_data["warmup_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["warmup_metrics"].get("avg_pace_seconds_per_km")
            )
        if "run_metrics" in performance_data:
            performance_data["run_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["run_metrics"].get("avg_pace_seconds_per_km")
            )
        if "recovery_metrics" in performance_data:
            performance_data["recovery_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["recovery_metrics"].get("avg_pace_seconds_per_km")
            )
        if "cooldown_metrics" in performance_data:
            performance_data["cooldown_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["cooldown_metrics"].get("avg_pace_seconds_per_km")
            )
        # Legacy support
        if "main_metrics" in performance_data:
            performance_data["main_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["main_metrics"].get("avg_pace_seconds_per_km")
            )
        if "finish_metrics" in performance_data:
            performance_data["finish_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["finish_metrics"].get("avg_pace_seconds_per_km")
            )

        # Generate heart rate zone pie chart data
        hr_zone_pie_data = self._generate_hr_zone_pie_data(activity_id)

        # Extract split highlights
        split_analysis_data = section_analyses.get("split_analysis", {})
        highlights_list = split_analysis_data.get("highlights", "N/A")

        # Generate interval graph analysis (for interval workouts only)
        training_type = performance_data.get("training_type", "aerobic_base")
        training_type_category = self._get_training_type_category(training_type)
        interval_graph_analysis = None
        if training_type_category == "interval_sprint" and splits_data:
            interval_graph_analysis = self._generate_mermaid_analysis(
                splits_data, training_type_category
            )

        # Prepare template context
        context = {
            "activity_id": str(activity_id),
            "date": date,
            "activity_name": performance_data.get("activity_name"),
            "location_name": performance_data.get("location_name"),
            "basic_metrics": performance_data.get("basic_metrics", {}),
            "weight_kg": performance_data.get("weight_kg"),
            "weather_data": performance_data.get("weather_data", {}),
            "gear_name": performance_data.get("gear_name"),
            "form_efficiency": performance_data.get("form_efficiency"),
            "performance_metrics": performance_data.get("performance_metrics"),
            "training_type": performance_data.get("training_type"),
            "training_type_category": training_type_category,
            "activity_type": self._get_activity_type_display(
                performance_data.get("training_type", "aerobic_base")
            ),
            "warmup_metrics": performance_data.get("warmup_metrics"),
            "run_metrics": performance_data.get("run_metrics"),
            "recovery_metrics": performance_data.get("recovery_metrics"),
            "cooldown_metrics": performance_data.get("cooldown_metrics"),
            "main_metrics": performance_data.get("main_metrics"),  # Legacy
            "finish_metrics": performance_data.get("finish_metrics"),  # Legacy
            "splits": splits_data,
            "efficiency": section_analyses.get("efficiency"),
            "environment_analysis": section_analyses.get("environment_analysis"),
            "phase_evaluation": section_analyses.get("phase_evaluation"),
            "split_analysis": section_analyses.get("split_analysis"),
            "summary": section_analyses.get("summary"),
            # Phase 3: Similar workouts comparison (from performance_data)
            "similar_workouts": performance_data.get("similar_workouts"),
            # Mermaid graph data
            "mermaid_data": performance_data.get("mermaid_data"),
            # Interval graph analysis
            "interval_graph_analysis": interval_graph_analysis,
            # Heart rate zone pie chart data
            "heart_rate_zone_pie_data": hr_zone_pie_data,
            # Split highlights
            "highlights_list": highlights_list,
            # Phase 2: Physiological data (VO2 Max, Lactate Threshold)
            "reference_info": performance_data.get("reference_info"),
            "vo2_max_data": performance_data.get("vo2_max_data"),
            "lactate_threshold_data": performance_data.get("lactate_threshold_data"),
            "show_physiological": training_type_category
            in ["tempo_threshold", "interval_sprint"],
            # Physiological indicators (calculated in _calculate_physiological_indicators)
            "vo2_max_utilization": performance_data.get("vo2_max_utilization"),
            "vo2_max_utilization_eval": performance_data.get(
                "vo2_max_utilization_eval"
            ),
            "threshold_pace_formatted": performance_data.get(
                "threshold_pace_formatted"
            ),
            "threshold_pace_comparison": performance_data.get(
                "threshold_pace_comparison"
            ),
            "ftp_percentage": performance_data.get("ftp_percentage"),
            "work_avg_power": performance_data.get("work_avg_power"),
        }

        # Render report using Jinja2 template with all data
        report_content = self.renderer.render_report(**context)

        logger.info("[4/4] Saving report to result/individual/...")

        # Save report
        save_result = self.renderer.save_report(str(activity_id), date, report_content)

        return {
            "success": True,
            "activity_id": activity_id,
            "date": date,
            "report_path": save_result["path"],
            "timestamp": datetime.now().isoformat(),
        }


def main():
    """Main entry point for report generator worker."""
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m tools.reporting.report_generator_worker <activity_id> [date]"
        )
        sys.exit(1)

    activity_id = int(sys.argv[1])
    date = sys.argv[2] if len(sys.argv) > 2 else None

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id, date)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
